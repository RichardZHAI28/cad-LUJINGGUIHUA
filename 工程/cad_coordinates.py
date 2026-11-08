"""CAD geometry always uses WCS, independently of robot workpiece teaching."""
CAD_COORDINATES = {'世界坐标（WCS）': 'wcs'}


def drawing_transform(doc, coordinate_system):
    if coordinate_system != 'wcs':
        raise ValueError('图纸固定使用世界坐标 WCS，不支持 UCS 换算')
    return None, ''
