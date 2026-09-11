import io
import struct
import unittest
import zipfile
import zlib

from no_ai_marks.metadata import scan_blob
from no_ai_marks.registry import default_registry

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
XMP_AI = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
    b'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/'
    b'trainedAlgorithmicMedia"/></rdf:RDF></x:xmpmeta>'
)


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png(*chunks):
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    return PNG_SIGNATURE + header + b"".join(chunks) + chunk(b"IEND", b"")


def jpeg(*segments):
    body = b"".join(struct.pack(">BBH", 0xFF, marker, len(data) + 2) + data for marker, data in segments)
    return b"\xff\xd8" + body + b"\xff\xda\x00\x02" + b"\x00" * 16 + b"\xff\xd9"


def rules(data):
    return [rule for rule, _ in scan_blob(data, default_registry())]


class MetadataTest(unittest.TestCase):
    def test_stable_diffusion_parameters(self):
        data = png(chunk(b"tEXt", b"parameters\0a castle, Steps: 20, Sampler: Euler"))
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_compressed_itxt_naming_generator(self):
        text = zlib.compress(b"Midjourney v7")
        data = png(chunk(b"iTXt", b"Software\0\x01\x00\0\0" + text))
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_ordinary_png(self):
        self.assertEqual(rules(png(chunk(b"tEXt", b"Software\0GIMP 2.10"))), [])

    def test_jpeg_exif_software(self):
        data = jpeg((0xE1, b"Exif\0\0MM\0*\0\0\0\x08Software\0DALL-E 3\0"))
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_jpeg_xmp_digital_source_type(self):
        data = jpeg((0xE1, b"http://ns.adobe.com/xap/1.0/\0" + XMP_AI))
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_c2pa_manifest_is_a_warning_rule(self):
        data = jpeg((0xEB, b"JP\0\x01jumb\0\0\0\x00jumdc2pa\0c2pa.claim\0"))
        self.assertEqual(rules(data), ["c2pa-manifest"])

    def test_pdf_producer(self):
        data = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Producer (ChatGPT) >>\nendobj\n%%EOF\n"
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_pdf_utf16_hex_creator(self):
        data = b"%PDF-1.7\n1 0 obj\n<< /Creator <FEFF0043006C0061007500640065> >>\nendobj\n"
        self.assertEqual(rules(data), ["ai-metadata"])

    def test_pdf_title_is_not_checked(self):
        data = b"%PDF-1.7\n1 0 obj\n<< /Title (Notes on Claude Shannon) /Producer (LaTeX) >>\nendobj\n"
        self.assertEqual(rules(data), [])

    def test_docx_application(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("docProps/app.xml", "<Properties><Application>Claude</Application></Properties>")
            z.writestr("word/document.xml", "<w:document/>")
        self.assertEqual(rules(buf.getvalue()), ["ai-metadata"])


if __name__ == "__main__":
    unittest.main()
