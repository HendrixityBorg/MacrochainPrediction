from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}


def _column(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + ord(character.upper()) - ord("A") + 1
    return value - 1


def _sheet_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall(".//m:sheet", NS):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            break
    if relationship_id is None:
        raise KeyError(sheet_name)
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall("p:Relationship", NS):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"]
            return target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
    raise KeyError(relationship_id)


def rows(path: Path, sheet_name: str) -> list[list[Any]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]
        root = ET.fromstring(archive.read(_sheet_target(archive, sheet_name)))
        output: list[list[Any]] = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            values: dict[int, Any] = {}
            for cell in row.findall("m:c", NS):
                index = _column(cell.attrib["r"])
                kind = cell.attrib.get("t")
                if kind == "inlineStr":
                    value: Any = "".join(node.text or "" for node in cell.findall(".//m:t", NS))
                else:
                    node = cell.find("m:v", NS)
                    value = None if node is None else node.text
                    if value is not None and kind == "s":
                        value = shared[int(value)]
                    elif value is not None:
                        try:
                            number = float(value)
                            value = int(number) if number.is_integer() else number
                        except ValueError:
                            pass
                values[index] = value
            if values:
                output.append([values.get(index) for index in range(max(values) + 1)])
    return output

