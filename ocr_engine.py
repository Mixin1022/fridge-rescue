"""Shared RapidOCR adapter; keep Chinese boxes and their original confidence."""
import re


class ChineseOCR:
    def __init__(self):
        from rapidocr import RapidOCR
        self.engine = RapidOCR()

    def readtext(self, image, **kwargs):
        result = self.engine(image)
        if result.txts is None:
            return []
        return [(box, str(text), float(score)) for box, text, score in zip(result.boxes, result.txts, result.scores)
                if re.search(r'[\u4e00-\u9fff]', str(text))
                and len(re.findall(r'[A-Za-z]', str(text))) <= len(re.findall(r'[\u4e00-\u9fff]', str(text)))]
