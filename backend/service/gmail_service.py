import re
import spacy

nlp = spacy.load("en_core_web_sm")

def extract_company(subject: str) -> str:
    patterns = [
        r"Thank you for applying to ([\w\s&\-!]+)", 
        r"Application received for .* at ([\w\s&\-!]+)", 
        r"Thank you for applying – ([\w\s&\-!]+)",   
        r"at ([\w\s&\-!]+)"                           
    ]
    for p in patterns:
        match = re.search(p, subject, re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip('!')
    return None

def extract_company_spacy(subject: str):
    doc = nlp(subject)
    for ent in doc.ents:
        if ent.label_ == "ORG":
            return ent.text
    return None
