
"""
Contains all data classes to hold the messages for a Report. The messages
can come from the CppCheck module, from the compiler or from the unit test
results.

Authors: Martin Wichmann, Christian Wichmann
"""

import json
import xml.etree.ElementTree


class ReportJSONEncoder(json.JSONEncoder):
    """
    Converts reports, report parts and messages into JSON strings. The default
    method returns a serializable object for all three classes containing report
    data. Every time either a report, a part of a report or a message has to be
    serialized to JSON, this encoder can be used:

    >>> json.dumps(some_report, default=ReportJSONEncoder)
    {"gcc": {"messages": [{"type": "", "line": "", "desc": "", "file": ""}, ...], "returncode": 0}, ...}
    """
    # TODO Write JSONDecoder.
    def default(self, obj):
        if isinstance(obj, Report):
            report_object = {}
            for report in obj.parts:
                report_object[report.source] = ReportJSONEncoder().default(report)
            return report_object
        elif isinstance(obj, ReportPart):
            report_part_object = {}
            report_part_object['returncode'] = obj.returncode
            report_part_object['messages'] = [ReportJSONEncoder().default(m) for m in obj.messages]
            if obj.tests:
                report_part_object['tests'] = obj.tests
            return report_part_object
        elif isinstance(obj, Message):
            message_part_object = {}
            # get all information from message object (all fields that are not inherited by object class)
            message_infos = filter(lambda x: x not in object.__dict__ , obj.__dict__.keys())
            for info in message_infos:
                message_part_object[info] = obj.__getattribute__(info)
            return message_part_object
        else:
            return super(ReportJSONEncoder, self).default(obj)


class Report(object):
    def __init__(self):
        self.parts = []

    def add_part(self, report_part):
        self.parts.append(report_part)

    def __str__(self):
        ret = ''
        for p in self.parts:
            ret += str(p)
        return ret

    def to_json(self):
        """
        Converts data from this report to JSON format. First all data from
        report parts and their messages are collected as dictionary. Then the
        whole dictionary can be dumped to JSON and be returned.

        :returns: string containing a JSON representation of this report
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of all report parts in this report and all
        messages inside these parts.

        :returns: string containing XML representation of this report
        """
        # TODO Check if some serialization library like pyxser would be better.
        report_root = xml.etree.ElementTree.Element('report')
        for part in self.parts:
            report_root.append(part.to_xml())
        return xml.etree.ElementTree.tostring(report_root)


class ReportPart(object):
    def __init__(self, source, returncode, messages, tests=None):
        self.source = source
        self.returncode = returncode
        self.messages = messages
        self.tests = tests

    def __str__(self):
        ret = '{} {}\n'.format(self.source, self.returncode)
        for m in self.messages:
            ret += '  ' + str(m) + '\n'
        return ret

    def to_json(self):
        """
        Converts data from this report part to JSON format. This includes all
        messages inside this part and the return code.

        :returns: string containing a JSON representation of this report part
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of this report part. It returns always the
        XML Element containing all data of this part.
        """
        attributes = {'returncode': str(self.returncode)}
        current_part = xml.etree.ElementTree.Element(self.source, attrib=attributes)
        # create sub-element for each message in report part
        for message in self.messages:
            current_part.append(message.to_xml())
        # TODO Add test results (self.tests) to XML output!
        return current_part


class Message(object):
    def __init__(self, _type, _file, line, desc):
        self.type = _type
        self.file = _file
        self.line = line
        self.desc = desc

    def __str__(self):
        return '{} {}:{} {}...'.format(self.type, self.file, self.line, self.desc[:40])

    def to_json(self):
        """
        Converts data from this message to JSON format. This includes at least
        the type, file name, line number and a description.

        :returns: string containing a JSON representation of this message
        """
        return json.dumps(self, cls=ReportJSONEncoder)

    def to_xml(self):
        """
        Builds a XML representation of this message. It returns always the XML
        Element containing all data of this message.
        """
        message_element = xml.etree.ElementTree.Element('message')
        # get all information from message object (all fields that are not inherited by object class)
        message_infos = filter(lambda x: x not in object.__dict__ , self.__dict__.keys())
        # append all messages as sub-elements
        for info in message_infos:
            new_sub_element = xml.etree.ElementTree.SubElement(message_element, info)
            new_sub_element.text = self.__getattribute__(info)
        return message_element
