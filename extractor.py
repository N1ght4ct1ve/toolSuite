import xml.etree.ElementTree as ET
import os

class Extractor:
    def __init__(self, filename):
        self.filename = filename

    def extract(self):
        _, ext = os.path.splitext(self.filename)
        if ext.lower() == '.txt':
            return self._extract_txt()
        else:
            return self._extract_xml()

    def _extract_txt(self):
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple heuristic: First line is title if short, else no title
            lines = content.split('\n')
            title = ""
            abstract = ""
            sections = []
            
            if lines and len(lines[0]) < 100:
                title = lines[0].strip()
                body_text = "\n".join(lines[1:]).strip()
            else:
                title = "Text Document"
                body_text = content.strip()
                
            sections.append({
                'section-title': '',
                'section-text': body_text
            })
            
            return title, abstract, sections
        except Exception as e:
            print(f"Error reading text file: {e}")
            return "", "", []

    def _extract_xml(self):
        try:
            tree = ET.parse(self.filename)
        except ET.ParseError:
            return "", "", []
            
        root = tree.getroot()

        # Namespace handling
        if '}' in root.tag:
            ns_url = root.tag.split('}')[0].strip('{')
            ns = {'jats': ns_url}
        else:
            ns = {}

        def find_all(element, path):
            if ns:
                return element.findall(path, ns)
            else:
                return element.findall(path.replace('jats:', ''))

        def find(element, path):
            if ns:
                return element.find(path, ns)
            else:
                return element.find(path.replace('jats:', ''))

        # Extract title
        title_elem = find(root, './/jats:article-title')
        title = ""
        if title_elem is not None:
            title = ''.join(title_elem.itertext()).strip()

        # Extract abstract
        abstract_elem = find(root, './/jats:abstract')
        abstract = ""
        if abstract_elem is not None:
            abstract = ''.join(abstract_elem.itertext()).strip()

        # Extract sections
        sections = []
        body = find(root, './/jats:body')
        if body is not None:
            for sec in find_all(body, './/jats:sec'):
                sec_title_elem = find(sec, 'jats:title')
                sec_title = sec_title_elem.text.strip() if sec_title_elem is not None and sec_title_elem.text else ""
                
                sec_texts = []
                for p in find_all(sec, 'jats:p'):
                    sec_texts.append(''.join(p.itertext()).strip())
                
                sec_text = "\n".join(sec_texts)
                
                if sec_title or sec_text:
                    sections.append({
                        'section-title': sec_title,
                        'section-text': sec_text
                    })

        return title, abstract, sections
