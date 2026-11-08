"""Place font outlines using DXF text anchors and cap heights.

Layout happens in local coordinates before size adjustment, OCS and insertion.
An MTEXT insertion point is an attachment point, not a glyph baseline.
"""
import math

from matplotlib.path import Path
from matplotlib.textpath import TextToPath
from matplotlib.transforms import Affine2D
from matplotlib.ft2font import FT2Font
from ezdxf.addons.text2path import alignment_transformation
from ezdxf.fonts.fonts import FontFace
from ezdxf.fonts.font_measurements import FontMeasurements
from ezdxf.math import BoundingBox2d, Matrix44
from ezdxf.render.abstract_mtext_renderer import AbstractMTextRenderer
from ezdxf.tools import text_layout as tl
from ezdxf.tools.text import MTextParser, TokenType, leading


class FontGeometry:
    """Use the validated CAD font, including private/substituted font files."""

    def __init__(self, font):
        self.font = font.copy()
        self.font.set_size(100)
        self.converter = TextToPath()
        self.paths = {}
        codes = FT2Font(self.font.get_file()).get_charmap()
        # Custom stencil fonts can contain only capitals/digits (ZITI1 lacks X).
        # Never measure .notdef as if it were a real X, x or p glyph.
        cap_char = next((ch for ch in 'XHNMIEA0123456789' if ord(ch) in codes), None)
        if cap_char is None:
            raise ValueError('字库缺少可测量的大写字母或数字，不能确定文字高度')
        cap = self.path(cap_char).get_extents()
        lower = self.path('x').get_extents() if ord('x') in codes else None
        descender = self.path('p').get_extents() if ord('p') in codes else None
        self.baseline = lower.ymin if lower is not None else 0.0
        self.cap = cap.ymax - self.baseline
        if not math.isfinite(self.cap) or self.cap <= 0:
            raise ValueError('无法读取字体的大写字高，不能确定 CAD 文字尺寸')
        self.measurements = FontMeasurements(
            0, 1, (lower.ymax-self.baseline)/self.cap if lower is not None else .7,
            max(0, (self.baseline-descender.ymin)/self.cap) if descender is not None else 0)

    def path(self, text):
        if text not in self.paths:
            # CAD content is literal text, including $ and _, never math markup.
            vertices, codes = self.converter.get_text_path(self.font, text, ismath=False)
            self.paths[text] = Path(vertices, codes)
        return self.paths[text]

    def width(self, text, height):
        width, _, _ = self.converter.get_text_width_height_descent(text, self.font, ismath=False)
        return width * height / self.cap

    def polygons(self, text, height):
        transform = Affine2D().translate(0, -self.baseline).scale(height/self.cap)
        return self.path(text).transformed(transform).to_polygons()


def transformed_paths(polygons, matrix):
    return [[(v.x, v.y) for v in matrix.transform_vertices((x, y, 0) for x, y in polygon)]
            for polygon in polygons if len(polygon) > 1]


class WordRenderer(tl.ContentRenderer):
    def __init__(self, output, geometry, text, ctx):
        self.output, self.geometry, self.text = output, geometry, text
        self.height, self.width, self.oblique = ctx.cap_height, ctx.width_factor, ctx.oblique

    def render(self, left, bottom, right, top, m=None):
        matrix = Matrix44.scale(self.width, 1, 1)
        matrix *= Matrix44.shear_xy(angle_x=math.radians(self.oblique))
        matrix *= Matrix44.translate(left, bottom, 0)
        if m is not None:
            matrix *= m
        self.output.extend(transformed_paths(self.geometry.polygons(self.text, self.height), matrix))

    def line(self, x1, y1, x2, y2, m=None):
        self.output.extend(transformed_paths([[(x1, y1), (x2, y2)]], m if m is not None else Matrix44()))


class MTextOutlines(AbstractMTextRenderer):
    def __init__(self, geometry):
        super().__init__()
        self.geometry = geometry
        self.output = []

    def word(self, text, ctx):
        return tl.Text(width=self.geometry.width(text, ctx.cap_height)*ctx.width_factor,
                       height=ctx.cap_height, valign=tl.CellAlignment(ctx.align),
                       stroke=self.get_stroke(ctx),
                       renderer=WordRenderer(self.output, self.geometry, text, ctx))

    def space_width(self, ctx):
        return self.geometry.width(' ', ctx.cap_height)*ctx.width_factor

    def fraction(self, data, ctx):
        upper, lower, kind = data
        if not kind:
            return self.word(upper, ctx)
        return tl.Fraction(top=self.word(upper, ctx), bottom=self.word(lower, ctx),
                           stacking=self.get_stacking(kind),
                           renderer=WordRenderer(self.output, self.geometry, '', ctx))

    def get_font_face(self, mtext):
        # No second font lookup or fallback inside the layout engine.
        return FontFace(filename=self.geometry.font.get_file(), family='CAD font')

    def make_bg_renderer(self, mtext):
        # A CAD editor's background mask is not material to weld.
        return tl.DoNothingRenderer()

    def natural_width(self, mtext):
        width = current = 0
        for token in MTextParser(mtext.all_columns_raw_content(), self.make_mtext_context(mtext)):
            ctx = token.ctx
            if token.type in (TokenType.NEW_PARAGRAPH, TokenType.NEW_COLUMN):
                width, current = max(width, current), 0
            elif token.type == TokenType.WORD:
                current += self.geometry.width(token.data, ctx.cap_height)*ctx.width_factor
            elif token.type in (TokenType.SPACE, TokenType.NBSP, TokenType.TABULATOR):
                current += self.space_width(ctx) * (4 if token.type == TokenType.TABULATOR else 1)
            elif token.type == TokenType.STACK:
                current += self.fraction(token.data, ctx).total_width
        return max(width, current, 1e-6)

    def outlines(self, entity, text_scale, coordinate_transform=None):
        layout_entity = entity.copy()
        # ezdxf 1.1 rounds 5/3 to 1.667. Avoid accumulating that rounding
        # error for tall text or many rows without changing the vendor library.
        layout_entity.dxf.line_spacing_factor *= (5/3)/leading(1)
        if entity.dxf.get('width', 0) < 1e-6 and not entity.has_columns:
            # Avoid approximate measurement with a separately resolved font for
            # zero-width (unwrapped) MTEXT, especially private font files.
            layout_entity.dxf.width = self.natural_width(entity) * (1+1e-10)
        layout = self.layout_engine(layout_entity)
        # AutoCAD includes rounded-letter overshoot above the cap line in each
        # line's ascent, and descenders in the block's bottom extent. Measuring
        # only nominal cap-height boxes leaves several millimetres of error in
        # a 200 mm C/Q, even after fixing the insertion/baseline mix-up.
        # Keep the layout engine's wrapping, paragraphs and horizontal alignment
        # while rendering each line in local coordinates to measure that ascent.
        attachment = entity.dxf.attachment_point
        layout.place(align=tl.LayoutAlignment((attachment-1)%3+1))
        output, bottom = [], 0
        for column in layout:
            ascent_adjustment = 0
            for paragraph in column:
                if isinstance(paragraph,tl.EmptyParagraph):
                    continue
                for line in paragraph:
                    # ezdxf 1.1's rigid groups place mixed-size words at the
                    # same top edge. Apply each word's vertical alignment to
                    # the line height so normal text shares a baseline.
                    for cell in line:
                        if isinstance(cell,tl.ContentCell):
                            x,_=cell.final_location()
                            cell.place(x,line.final_location()[1]+tl.vertical_cell_shift(cell,line.total_height))
                    self.output.clear()
                    line.render()
                    points = [p for path in self.output for p in path]
                    if points:
                        # MTEXT aligns the visible line extent, unlike TEXT's
                        # advance width. Positive initial side bearing is
                        # excluded, while a negative overhang remains visible.
                        start=line.final_location()[0]
                        ink_left=max(start,min(x for x,y in points))
                        ink_right=max(x for x,y in points)
                        advance=sum(cell.total_width for cell in line.cells())
                        if isinstance(line,tl.CenterLine):
                            horizontal_shift=start+advance/2-(ink_left+ink_right)/2
                        elif isinstance(line,tl.RightLine):
                            horizontal_shift=start+advance-ink_right
                        else:
                            horizontal_shift=start-ink_left
                        ascent_adjustment += max(0, max(y for x,y in points)-line.final_location()[1])
                        output.extend([[(x+horizontal_shift,y-ascent_adjustment) for x,y in path] for path in self.output])
            bottom = min(bottom, column.final_location()[1]-column.total_height-ascent_adjustment)
        if output:
            bottom = min(bottom, min(y for path in output for x,y in path))
        vertical_shift = -bottom*((attachment-1)//3)/2
        matrix = (Matrix44.translate(0,vertical_shift,0)
                  @ Matrix44.scale(text_scale,text_scale,1) @ entity.ucs().matrix)
        if coordinate_transform is not None:
            matrix *= coordinate_transform
        return transformed_paths(output,matrix)


def text_outlines(entity, font, text_scale, coordinate_transform=None):
    geometry = FontGeometry(font)
    if entity.dxftype() == 'MTEXT':
        return MTextOutlines(geometry).outlines(entity, text_scale, coordinate_transform)

    text = entity.plain_text()
    if not text.strip():
        return []
    height = entity.dxf.height
    measurements = geometry.measurements.scale(height)
    # Use advance width, including side bearings/spacing, for alignment and
    # FIT/ALIGNED constraints instead of the painted glyph's bounding box.
    bounds = BoundingBox2d([(0, -measurements.descender_height),
                            (geometry.width(text, height), height)])
    alignment = alignment_transformation(measurements, bounds, entity.get_align_enum(),
                                         entity.fit_length())
    matrix = (alignment @ Matrix44.scale(text_scale, text_scale, 1)
              @ entity.wcs_transformation_matrix())
    if coordinate_transform is not None:
        matrix *= coordinate_transform
    return transformed_paths(geometry.polygons(text, height), matrix)
