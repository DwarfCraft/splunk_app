"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import qrcode
import qrcode.image.svg
import StringIO

FILE_TYPES = [{
    'extension': 'png',
    'name': 'PNG',
}, {
    'extension': 'svg',
    'name': 'SVG',
}]


def generate_qr_code(input_str, type_str):
    """

    :param input_str: String to embed in QR code
    :param type_str: File type of QR (e.g. png, jpg)
    :return: Encoded QR code file
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(input_str)

    if type_str == 'png':
        from qrcode.image.pure import PymagingImage
        img = qr.make_image(image_factory=PymagingImage)
        output = StringIO.StringIO()
        img.save(output)
        return output.getvalue()
    elif type_str == 'svg':
        factory = qrcode.image.svg.SvgImage
        img = qr.make_image(image_factory=factory)
        output = StringIO.StringIO()
        img.save(output)
        return output.getvalue()
    else:
        return 'Not valid'


def get_valid_file_types(with_names=True):
    if with_names:
        return FILE_TYPES
    return list(map(lambda x: x['extension'], FILE_TYPES))
