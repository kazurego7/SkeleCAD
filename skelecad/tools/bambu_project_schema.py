"""Empty editable 3MF structure; no generated model or private template required."""
from xml.etree import ElementTree as ET
from print_package_audit import NS, PNS, set_meta

IDENTITY = '1 0 0 0 1 0 0 0 1 0 0 0'


def empty_project():
    ET.register_namespace('', NS[1:-1])
    ET.register_namespace('p', PNS[1:-1])
    def model():
        root = ET.Element(NS+'model', {'unit': 'millimeter', 'requiredextensions': 'p',
                                      '{http://www.w3.org/XML/1998/namespace}lang': 'en-US'})
        ET.SubElement(root, NS+'metadata', name='BambuStudio:3mfVersion').text = '1'
        return root
    root = model()
    ET.SubElement(root, NS+'metadata', name='Application')
    ET.SubElement(root, NS+'metadata', name='Title')
    resources = ET.SubElement(root, NS+'resources')
    obj = ET.SubElement(resources, NS+'object', {'id':'2', 'type':'model', PNS+'UUID':''})
    components = ET.SubElement(obj, NS+'components')
    ET.SubElement(components, NS+'component', {'objectid':'1', PNS+'path':'', PNS+'UUID':'', 'transform':IDENTITY})
    build = ET.SubElement(root, NS+'build')
    item = ET.SubElement(build, NS+'item', {'objectid':'2', 'printable':'1', 'auto_drop':'1'})
    node = model()
    mesh_obj = ET.SubElement(ET.SubElement(node, NS+'resources'), NS+'object',
                             {'id':'1', 'type':'model', PNS+'UUID':''})
    ET.SubElement(mesh_obj, NS+'mesh')
    ET.SubElement(node, NS+'build')
    objmd = ET.Element('object', id='2')
    set_meta(objmd, 'extruder', 1)
    part = ET.SubElement(objmd, 'part', id='1', subtype='normal_part')
    for key, value in {'matrix':'1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1',
                       'source_object_id':'0', 'source_volume_id':'0'}.items():
        set_meta(part, key, value)
    payload = {
        '[Content_Types].xml': b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
        '_rels/.rels': b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
    }
    return root, obj, item, objmd, node, payload
