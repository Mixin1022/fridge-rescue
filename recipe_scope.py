"""Temporal scope hints, not authoritative deletion of ambiguous recipe evidence."""
import re
from content_classifier import PACKAGING

def scope_hints(records):
    hints={};scope='main'
    for i,r in sorted(enumerate(records),key=lambda pair:(pair[1].get('start',0),pair[0])):
        text=r['text']
        if PACKAGING.search(text):hints[i]='packaging';continue
        if re.search(r'饮品\s*[:：]|果茶|搭配.*红茶|闷好的红茶',text):scope='side_drink'
        elif re.search(r'司康.*烤好|挤满.*馅|组装|装盘',text):scope='main'
        elif re.search(r'制作.*馅|来做.*馅|奶油奶酪',text):scope='filling'
        hints[i]=scope
    return hints
