# -*- coding: utf-8 -*-
from email import header
from email.base64mime import header_length
from itertools import count
from tkinter.ttk import Separator
import pandas as pd
import io
import os
import re
import ast
import json
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
from dateutil.parser import parse
from contextlib import redirect_stderr
from csv import Sniffer

import chardet

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS
from rdflib.plugins.sparql import prepareQuery

#MSEO_URL = 'https://raw.githubusercontent.com/Mat-O-Lab/MSEO/main/MSEO_mid.owl'
#CCO_URL = 'https://github.com/CommonCoreOntology/CommonCoreOntologies/raw/master/cco-merged/MergedAllCoreOntology-v1.3-2021-03-01.ttl'
#CCOMU_URL = 'https://raw.githubusercontent.com/CommonCoreOntology/CommonCoreOntologies/master/UnitsOfMeasureOntology.ttl'
#QUDT_URL = 'http://www.qudt.org/qudt/owl/1.0.0/unit.owl'
#QUDT_UNIT_URL = 'http://qudt.org/2.1/vocab/unit'
QUDT_UNIT_URL = 'https://github.com/qudt/qudt-public-repo/raw/master/vocab/unit/VOCAB_QUDT-UNITS-ALL-v2.1.ttl'
QUDT = Namespace("http://qudt.org/schema/qudt/")

sub_classes = prepareQuery(
    "SELECT ?entity WHERE {?entity rdfs:subClassOf* ?parent}"
    )


def get_entities_with_property_with_value(graph, property, value):
    return [s for s, p, o in graph.triples((None,  property, value))]


#mseo_graph = Graph()
#mseo_graph.parse(CCO_URL, format='turtle')
#mseo_graph.parse(MSEO_URL, format='xml')

units_graph = Graph()
units_graph.parse(QUDT_UNIT_URL, format='turtle')
# will not use CCO Units anymore QUDT is more mature
#units_graph.parse(CCOMU_URL, format='turtle')
#units_graph.parse(MSEO_URL, format='xml')


# print(get_entities_with_property_with_value(
#     units_graph, SI_unit_symbol, Literal('min')))
#
# print(get_entities_with_property_with_value(
#     units_graph, alternative_label, Literal('mm', lang='en')))
#
#print(get_entities_with_property_with_value(
#    units_graph, QUDT.ucumCode, Literal('mm', datatype=QUDT.UCUMcs)))


class CSV_Annotator():
    def __init__(self, separator: str, header_separator: str, encoding: str):

        self.separator = separator
        self.header_separator = header_separator
        self.encoding = encoding

        self.json_ld_context = [
            "http://www.w3.org/ns/csvw", {
                #"cco": "http://www.ontologyrepository.com/CommonCoreOntologies/",
                #"mseo": "https://purl.matolab.org/mseo/mid/",
                "oa": "http://www.w3.org/ns/oa#",
                "label": "http://www.w3.org/2000/01/rdf-schema#label",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                "qudt": "http://qudt.org/schema/qudt/"
                }
        ]
        self.umlaute_dict = {
            '\u00e4': 'ae',  # U+00E4	   \xc3\xa4
            '\u00f6': 'oe',  # U+00F6	   \xc3\xb6
            '\u00fc': 'ue',  # U+00FC	   \xc3\xbc
            '\u00c4': 'Ae',  # U+00C4	   \xc3\x84
            '\u00d6': 'Oe',  # U+00D6	   \xc3\x96
            '\u00dc': 'Ue',  # U+00DC	   \xc3\x9c
            '\u00df': 'ss',  # U+00DF	   \xc3\x9f
        }
        self.superscripts_replace = {
            #'\u2070':°,
            '\u00b9':'',
            '\u00b2':'2',
            '\u00b3':'3',
            '\u2074':'4',
            '\u2075':'5',
            '\u2076':'6',
            '\u2077':'7',
            '\u2078':'8',
            '\u2079':'9',
            '\u00b0C':'Cel', #for °C
        }
    def open_file(self, uri=''):
        try:
            uri_parsed = urlparse(uri)
        except:
            print('not an uri - if local file add file:// as prefix')
            return None
        else:
            filename = unquote(uri_parsed.path).split('/')[-1]
            if uri_parsed.scheme in ['https', 'http']:
                filedata = urlopen(uri).read()

            elif uri_parsed.scheme == 'file':
                filedata = open(unquote(uri_parsed.path), 'rb').read()
            else:
                print('unknown scheme {}'.format(uri_parsed.scheme))
                return None
            return filedata, filename

    def process(self, url) -> (str, str):
        '''
        :return: returns a filename and content(json string dump) of a metafile in the json format.
        '''

        file_data, file_name = self.open_file(url)

        if file_name is None or file_data is None:
            return "error", "cannot parse url"

        if self.encoding == 'auto':
            self.encoding = self.get_encoding(file_data)

        if self.separator == 'auto':
            separator = self.get_column_separator(file_data)
            if not separator:
                return "error", 'cant find separator, pls manualy select'
            else:
                self.separator=separator
        #print(self.encoding,self.separator)
        metafile_name, result = self.process_file(file_name, file_data, self.separator, self.header_separator, self.encoding)

        return metafile_name, result

    def get_encoding(self, file_data):
        """

        :param file_data:   content of the file we want to parse
        :return:            encoding of the specified file content e.g. utf-8, ascii..
        """
        result = chardet.detect(file_data)
        return result['encoding']

    def get_column_separator(self, file_data: bytes, rownum = None):
        """

        :param file_data: data of the file we want to parse
        :param rownum: index of row ind data to test, if None uses last one by default
        :return:          the seperator of the specified data, e.g. ";" or ","
        """
        file_io = io.BytesIO(file_data)
        if rownum != None:
            test_line=file_io.readlines()[rownum]
        else:
            file_io.seek(-2048,os.SEEK_END)
            test_line=file_io.readlines()[-1]
        #print(test_line.decode(self.encoding))
        sniffer = Sniffer()
        try:
            dialect = sniffer.sniff(test_line.decode(self.encoding),delimiters=[";","\t","|"])
            return dialect.delimiter
        except:
            try:
                dialect = sniffer.sniff(test_line.decode(self.encoding))
                return dialect.delimiter
            except: 
                return None
        

    # define generator, which yields the next count of
    # occurrences of separator in row
    def generate_col_counts(self, file_data, separator, encoding):
        sep_regex = re.compile(separator.__str__())
        with io.StringIO(file_data.decode(encoding)) as f:
            row = f.readline()
            while (row != ""):
                # match with re instead of count() function!
                yield len(sep_regex.findall(row)) + 1
                row = f.readline()
            return

    def get_table_charateristics(self, file_data: bytes, separator: str, encoding: str) -> (int, int):
        """
        This method finds the beginning of a header line inside a csv file,
        aswell as the number of columns of the datatable
        :param file_data: content of the file we want to parse as bytes
        :param separator_string: csv-separator, will be interpretet as a regex
        :param encoding: text encoding
        :return: a 2-tuple of (counter, num_cols)
                      where
                          counter : index of the header line in the csv file
                          num_cols : number of columns in the data-table
        """
        last_line = b''
        num_cols = 0
        sep_regex = re.compile(separator.__str__())

        with io.BytesIO(file_data) as f:

            f.seek(-2, os.SEEK_END)

            cur_char = f.read(1)

            # edgecase that there is no \n at the end of file
            if(cur_char != b'\n'):
                cur_char = f.read(1)

            while(cur_char == b'\n' or cur_char == b'\r'):
                f.seek(-2, os.SEEK_CUR)
                cur_char = f.read(1)

            while cur_char != b'\n':
                last_line = cur_char + last_line
                f.seek(-2, os.SEEK_CUR)
                cur_char = f.read(1)

            num_cols = len(sep_regex.findall(
                last_line.decode(encoding))) + 1

        counter = 0
        # iter over column counts from end of file, if column count changes start of data table reached
        col_counts=list(enumerate(self.generate_col_counts(file_data=file_data, separator=separator, encoding=encoding)))
        #max_cols=col_counts[-1][1]
        runs=0
        col_counts.reverse()
        for rownum, count in col_counts:
            if runs==0:
                max_cols=count
            if count!=max_cols:
                return rownum+1, max_cols
            runs+=1
        return 0, max_cols

    def get_num_header_rows_and_dataframe(self, file_data, separator_string, header_length, encoding):
        """

        :param file_data: content of the file we want to parse
        :param separator_string: csv-delimiter
        :param header_length: rows of the header
        :param encoding: csv-encoding
        :return: 2-tuple (num_header_rows, table_data)
                      where
                          num_header_rows : number of header rows
                          table_data : pandas DataFrame object containing the tabular information
        """
        #print(separator_string, header_length, encoding)
        file_string = io.StringIO(file_data.decode(encoding))
        #skip lines already processed
        num_header_rows=0
        counter=0
        for row in range(header_length):
            file_string.readline()
        for line in file_string:
            #print(line)
            tests=[self.get_value_type(
                string) == 'TEXT' for string in line.split(separator_string)]
            #print(tests)
            all_text = all(tests)
            if all_text:
                counter += 1
                continue
            else:
                num_header_rows=counter
                break
        #print(num_header_rows,list(range(num_header_rows)))
        file_string.seek(0)
        try: 
            table_data = pd.read_csv(file_string, header= list(range(num_header_rows)), sep=separator_string,
            skiprows=header_length, encoding=encoding)
        except:
            table_data=pd.DataFrame()
        #print(table_data)
        # good_readout = False
        # while not good_readout:
        #     file_string.seek(0)
        #     # table_data = pd.read_csv(file_string, header=list(range(num_header_rows)), sep=separator_string,
        #                              skiprows=header_length, encoding=encoding)

        #     # test if all text values in first table row -> is a second header row
        #     all_text = all([self.get_value_type(
        #         value) == 'TEXT' for column, value in table_data.iloc[0].items()])
        #     if all_text:
        #         num_header_rows += 1
        #         continue
        #     else:
        #         good_readout = True
        return num_header_rows, table_data

    def get_unit(self, string):
        # remove possible braces
        string=string.strip("[]").strip("()")
        #get rid of superscripts
        for k in self.superscripts_replace.keys():
            string = string.replace(k, self.superscripts_replace[k])
        string=string.replace('N/mm\u00b2','N.m.m-2')
        string=string.replace('Nm','N.m')
        
        found = get_entities_with_property_with_value(
                units_graph, QUDT.Symbol, Literal(string)) \
                + get_entities_with_property_with_value(
                    units_graph, QUDT.ucumCode,
                    Literal(string, datatype=QUDT.UCUMcs)
                    )
        # will only look up qudt now, seams more mature
        if found:
            return {"qudt:unit": {"@id": str(found[0]), "@type": units_graph.value(found[0], RDF.type)}}
        else:
            return {}

    def is_date(self, string, fuzzy=False):
        try:
            parse(string, fuzzy=fuzzy)
            return True

        except ValueError:
            return False

    def get_value_type(self, string):
        string = str(string)
        # remove spaces and replace , with . and
        string = string.strip().replace(',', '.')
        if len(string) == 0:
            return 'BLANK'
        try:
            t = ast.literal_eval(string)
        except ValueError:
            return 'TEXT'
        except SyntaxError:
            if self.is_date(string):
                return 'DATE'
            else:
                return 'TEXT'
        else:
            if type(t) in [int, float, bool]:
                if type(t) is int:
                    return 'INT'
                if t in set((True, False)):
                    return 'BOOL'
                if type(t) is float:
                    return 'FLOAT'
            else:
                return 'TEXT'

    def describe_value(self, value_string):
        #remove leading and trailing white spaces
        if pd.isna(value_string):
            return {}
        elif self.get_value_type(value_string) == 'INT':
            return {"@type": "qudt:Quantity",'qudt:value': {'@value': int(value_string), '@type': 'xsd:integer'}}
        elif self.get_value_type(value_string) == 'BOOL':
            return {"@type": "qudt:Quantity",'qudt:value': {'@value': bool(value_string), '@type': 'xsd:boolean'}}
        elif self.get_value_type(value_string) == 'FLOAT':
            return {"@type": "qudt:Quantity",'qudt:value': {'@value': float(value_string), '@type': 'xsd:decimal'}}
        elif self.get_value_type(value_string) == 'DATE':
            return {"@type": "qudt:Quantity",'qudt:value': {'@value': str(parse(value_string).isoformat()), '@type': 'xsd:dateTime'}}
        else:
            return {
                "@type": "oa:TextualBody",
                "@purpose": "oa:tagging",
                "@value": value_string.strip()
            }
                #return {"@type": "qudt:Quantity",'qudt:value': {'@value': value_string, '@type': 'xsd:string'}}

    def make_id(self, string, filename=None):
        for k in self.umlaute_dict.keys():
            string = string.replace(k, self.umlaute_dict[k])
        if filename:
            return filename + '/' + re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))
        else:
            return re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))

    def get_additional_header(self, file_data: bytes, header_lenght: int = 0, header_separator='auto', encoding: str = 'utf-8') -> pd.DataFrame: 
        """

        :param file_data: content of the file we want to parse
        :param header_lenght: lenght of the additional header at start of csv file in count of rows
        :param encoding: text encoding
        :return:
        """
        if header_lenght:
            #test the last additional header line for the separator
            if header_separator=='auto':
                header_separator = self.get_column_separator(file_data, rownum=header_lenght-1)
            #find max colum count
            gen=self.generate_col_counts(file_data=file_data, separator=header_separator, encoding=encoding)
            col_count=list(next(gen) for rows in range(header_lenght))
            #print(col_count)
            #print(header_lenght, header_separator)
            file_string = io.StringIO(file_data.decode(encoding))
            header_df = pd.read_csv(file_string, header=None, sep=header_separator, nrows=header_lenght,
                                      names=range(max(col_count)),
                                      encoding=encoding,
                                      skip_blank_lines=False)
            header_df['row'] = header_df.index
            header_df.rename(columns={0: 'param'}, inplace=True)
            header_df.set_index('param', inplace=True)
            header_df = header_df[~header_df.index.duplicated()]
            header_df.dropna(thresh=2, inplace=True)
            #print(header_df)
            return header_df

        else:
            return None

    def serialize_header(self, header_data, filename=None):

        params = list()
        info_line_iri = "oa:Annotation"
        for parm_name, data in header_data.to_dict(orient='index').items():
            # describe_value(data['value'])
            # try to find unit if its last part and separated by space in label
            #print(parm_name)
            body=list()
            if parm_name[-1]==":":
                parm_name=parm_name[:-1]
            if len(parm_name.split(' ')) > 1:
                unit_json = self.get_unit(parm_name.rsplit(' ',1)[-1])
            else:
                unit_json = {}
            if unit_json:
                parm_name=parm_name.rsplit(' ', 1)[0]
                body.append({**{"@type": "qudt:Quantity",},**unit_json})

            para_dict = {'@id': self.make_id(parm_name)+str(
                data['row']), 'label': parm_name.strip(), '@type': info_line_iri}
            for col_name, value in data.items():
                #print(body)
                #print(parm_name,col_name, value,type(value))
                if col_name == 'row':
                    para_dict['rownum'] = {
                        "@value": data['row'], "@type": "xsd:integer"}
                # check if its a unit
                # if unit occurres before values in the line
                elif isinstance(value, str):
                    #if unit found in label no need to test further
                    toadd={}
                    if not unit_json:
                        unit_dict = self.get_unit(value.strip())
                        toadd=unit_dict
                    if not toadd:
                        toadd=self.describe_value(value)
                    if toadd:
                        #print(toadd)
                        if toadd.get('@type') == 'qudt:Quantity':
                            if any(entry.get('@type') == 'qudt:Quantity' for entry in body):
                                for entry in body:
                                    if entry.get('@type') == 'qudt:Quantity':
                                        entry.update({**entry,**toadd})
                                        break
                            else:
                                body.append(toadd)
                        else:
                            body.append(toadd)
                else:
                    toadd=self.describe_value(value)
                    if toadd:
                        body.append(toadd)
            #print(body)
            para_dict['oa:hasBody']=body
            params.append(para_dict)
        # print(params)
        return params

    def process_file(self, file_name, file_data, separator, header_separator, encoding, file_namespace=None):
        """

        :param file_name: name of the file we want to process
        :param file_data: content of the file
        :param separator: csv-seperator /delimiter of the data table part
        :param header_separator: csv-seperator /delimiter of the additianl header that might occure before
        :param encoding:  text-encoding (e.g. utf-8..)
        :return: a 2-tuple (meta_filename,result)
                      where
                          result :    the resulting metadata on how to
                                      read the file (skiprows, colnames ..)
                                      as a json dump
                          meta_filename :  the name of the metafile we want to write
        """

        # init results dict
        data_root_url = "https://github.com/Mat-O-Lab/resources/"

        if not file_namespace:
            file_namespace = ''
        metadata_csvw = dict()
        metadata_csvw["@context"] = self.json_ld_context        

        metadata_csvw["@id"]=file_namespace
        metadata_csvw["url"] = file_name
        data_table_header_row_index, data_table_column_count = self.get_table_charateristics(
            file_data, separator, encoding)
        #print(data_table_header_row_index)
        # print(data_table_header_row_index, data_table_column_count)
        # read additional header lines and provide as meta in results dict
        if data_table_header_row_index != 0:
            header_data = self.get_additional_header(
                file_data, data_table_header_row_index, header_separator,encoding)
            #print(header_data)
            if not header_data.empty:
                # print("serialze additinal header")
                metadata_csvw["notes"] = self.serialize_header(
                    header_data, filename=file_name)
        #print(metadata_csvw["notes"])
        # read tabular data structure, and determine number of header lines for column description used
        header_lines, table_data = self.get_num_header_rows_and_dataframe(
            file_data, separator, data_table_header_row_index, encoding)
        # describe dialect
        metadata_csvw["dialect"] = {"delimiter": separator,
                                    "skipRows": data_table_header_row_index, "headerRowCount": header_lines, "encoding": encoding}
        #print(metadata_csvw["dialect"])
        # describe columns
        if not table_data.empty:
            if header_lines == 1:
                # see if there might be a unit string at the end of each title
                # e.g. "E_y (MPa)"
                column_json = list()
                for index, title in enumerate(table_data.columns):

                    # skip Unnamed cols
                    if "Unnamed" in title:
                        continue
                    # try to find unit if its last part and separated by space in title
                    if len(title.split(' ')) > 1:
                        unit_json = self.get_unit(title.rsplit(' ',1)[-1])
                    else:
                        unit_json = {}
                    if unit_json:
                        title=title.rsplit(' ', 1)[0]
                    json_str = {
                        **{'titles': title, '@id': self.make_id(title), "@type": "Column"}, **unit_json}
                    column_json.append(json_str)
                metadata_csvw["tableSchema"] = {"columns": column_json}

            else:
                column_json = list()
                for index, (title, unit_str) in enumerate(table_data.columns):
                    json_str = {**{'titles': title, '@id': self.make_id(title), "@type": "Column"},
                                **self.get_unit(unit_str)}
                    column_json.append(json_str)
                metadata_csvw["tableSchema"] = {"columns": column_json}
        result = json.dumps(metadata_csvw, indent=4)
        meta_file_name = file_name.split(sep='.')[0] + '-metadata.json'
        return meta_file_name, result

    def set_encoding(self, new_encoding: str):
        self.encoding = new_encoding

    def set_separator(self, new_separator: str):
        self.separator = new_separator
