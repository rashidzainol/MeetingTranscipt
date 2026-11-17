"""Smoke tests for the Word / PDF export helpers.

Run with:  python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meeting_transcriber import MeetingTranscriber


SAMPLE = {
    "meeting_name": "Mesyuarat Pengurusan Q3",
    "meeting_date": "2026-11-17",
    "start_time": "09:00",
    "end_time": "10:30",
    "duration_seconds": 5400,
    "detected_language": "ms",
    "participants": ["Rashid Zainol", "Ahmad bin Ali"],
    "segments": [
        {"start": 0, "end": 12, "text": "Selamat pagi semua."},
        {"start": 12, "end": 45, "text": "Laporan kewangan suku ketiga \u2014 \u201cbaik\u201d."},
        {"start": 45, "end": 90, "text": "Tindakan: hantar dokumen sebelum 30 November."},
    ],
}


class ExportTests(unittest.TestCase):
    def test_export_docx(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "minutes.docx")
            MeetingTranscriber.export_docx(SAMPLE, path)
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(2), b"PK")  # OOXML zip
            self.assertGreater(os.path.getsize(path), 5000)

    def test_export_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "minutes.pdf")
            MeetingTranscriber.export_pdf(SAMPLE, path)
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(4), b"%PDF")
            self.assertGreater(os.path.getsize(path), 1000)

    def test_pdf_handles_non_latin1(self):
        data = dict(SAMPLE, meeting_name="Mesyuarat \U0001F600 \u2014 khas")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "emoji.pdf")
            MeetingTranscriber.export_pdf(data, path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
