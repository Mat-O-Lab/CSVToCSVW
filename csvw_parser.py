
from typing import Tuple, List
import pandas as pd
from rdflib import BNode, URIRef, Literal, Graph
from rdflib.util import guess_format
from rdflib.namespace import CSVW, RDF, XSD, PROV, RDFS
from datetime import datetime
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
import io

def parse_csv_from_url_to_list(csv_url,delimiter: str=',', skiprows:int =0, num_header_rows: int=2, encoding: str='utf-8') -> List[List]:
    """Parses a csv file using the dialect given, to a list containing the content of every row as list.

    Args:
        csv_url (_type_): Url to the csv file to parse
        delimiter (str, optional): Delimiter for columns. Defaults to ','.
        skiprows (int, optional): Rows to Skip reading. Defaults to 0.
        num_header_rows (int, optional): Number of header rows with names of columns. Defaults to 2.
        encoding (str, optional): Encoding of the csv file. Defaults to 'utf-8'.

    Returns:
        List[List]: List of Lists with entrys for each row. Content of header rows are not included
    """
    file_data, file_name = open_csv(csv_url)
    file_string = io.StringIO(file_data.decode(encoding))
    table_data = pd.read_csv(file_string, header= list(range(num_header_rows)), sep=delimiter, skiprows=num_header_rows+skiprows, encoding=encoding)
    # add a row index column
    line_list=table_data.to_numpy().tolist()
    line_list=[ [index,]+line for index, line in enumerate(line_list)]
    return line_list

def open_csv(uri: str) -> Tuple[str,str]:
    """Open a csv file for reading, returns filedata and filename in a Tuple.

    Args:
        uri (str): Uri to the file to read

    Returns:
        Tuple[str,str]: Tuple of filedata and filename
    """
    print('try to open: {}'.format(uri))
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

def parse_graph(url: str, graph: Graph, format: str = '') -> Graph:
    """Parse a Graph from web url to rdflib graph object
    Args:
        url (AnyUrl): Url to an web ressource
        graph (Graph): Existing Rdflib Graph object to parse data to.
    Returns:
        Graph: Rdflib graph Object
    """
    parsed_url=urlparse(url)
    if not format:
        format=guess_format(parsed_url.path)
    if parsed_url.scheme in ['https', 'http']:
        graph.parse(urlopen(parsed_url.geturl()).read(), format=format)

    elif parsed_url.scheme == 'file':
        print(parsed_url.path)
        graph.parse(parsed_url.path, format=format)
    return graph


class CSVWtoRDF:
    """Class for Converting CSV data to RDF with help of CSVW Annotations
    """
    def __init__(self,metadata_url: str, csv_url: str, api_url: None, metaformat: str="json-ld") -> None:
        self.metadata_url=metadata_url
        self.api_url=api_url
        # get metadata graph
        self.metagraph=parse_graph(metadata_url,Graph(),format=metaformat)
        self.meta_root, url=list(self.metagraph[:CSVW.url])[0]
        self.graph=Graph()
        self.base_url="{}/".format(str(self.meta_root).rsplit('/',1)[0])
        parsed_url=urlparse(url)
        if parsed_url.scheme in ['https', 'http', 'file']:
            self.csv_url=url
        else:
            self.csv_url=self.base_url+url
        # replace if set in request
        if csv_url:
            self.csv_url=csv_url
        print(self.metadata_url,self.csv_url)
        self.file_url=self.csv_url.rsplit('.',1)[0]+".ttl"
        dialect=next(self.metagraph[self.meta_root : CSVW.dialect],None)
        self.dialect_dict={k: v.value for (k,v) in self.metagraph[dialect:]}
        print(self.dialect_dict)
        self.table_schema_node=next(self.metagraph[ self.meta_root: CSVW.tableSchema: ],None)
        self.table_aboutUrl=next(self.metagraph[self.table_schema_node : CSVW.aboutUrl],None)
        columns=self.metagraph[ : RDF.type : CSVW.Column]
        self.columns=[(column,{ k: v for (k,v) in self.metagraph[column:]}) for column in columns]
        print(len(self.columns))
        # get table form csv_url
        if self.table_schema_node:
            self.table = parse_csv_from_url_to_list(
                self.csv_url,
                delimiter=self.dialect_dict[CSVW.delimiter],
                skiprows=self.dialect_dict[CSVW.skipRows],
                num_header_rows=self.dialect_dict[CSVW.headerRowCount],
                encoding=self.dialect_dict[CSVW.encoding],
                )
        else:
            self.table=list()
    def convert_table(self) -> Graph:
        g=Graph()
        g.bind("csvw", CSVW)
        table_group=BNode()
        g.add((table_group,RDF.type,CSVW.TableGroup))
        table=BNode()
        g.add((table_group,CSVW.table, table))
        g.add((table,RDF.type,CSVW.Table))
        if self.table_aboutUrl:
            row_uri=self.table_aboutUrl
        else:
            row_uri='#gid-{GID}'
        for index,row in enumerate(self.table):
            row_node=BNode()
            value_node=URIRef(row_uri.format(GID=index))
            g.add((table,CSVW.row,row_node))
            g.add((row_node, RDF.type, CSVW.Row))
            g.add((row_node, CSVW.describes, value_node))
            g.add((row_node, CSVW.url, URIRef('{}/row={}'.format(self.csv_url,index+self.dialect_dict[CSVW.skipRows]+self.dialect_dict[CSVW.headerRowCount]))))
            for cell_index, cell in enumerate(row):
                #print(self.columns[cell_index])
                column=self.columns[cell_index][0]
                format=self.columns[cell_index][1].get('format', XSD.string)
                if self.columns[cell_index][1][CSVW.name]==Literal('GID'):
                    continue
                else:
                    if isinstance(column,URIRef): #has proper uri
                        g.add((value_node, column, Literal(cell)))
                    elif CSVW.aboutUrl in self.columns[cell_index][1].keys():
                        aboutUrl=self.columns[cell_index][1][CSVW.aboutUrl]
                        g.add((value_node, URIRef(aboutUrl.format(GID=index)), Literal(cell, datatype=format)))
                    else:
                        url=self.columns[cell_index][1][CSVW.name]
                        g.add((value_node, URIRef("{}/{}".format(self.metadata_url.rsplit('/',1)[0],url)), Literal(cell, datatype=format)))
        return g
        #self.atdm, self.metadata =converter.convert_to_atdm('standard')
    def convert(self,format: str='turtle') -> str:
        graph=self.convert_table() 
        graph.bind('base',self.base_url, override=True)
        if self.api_url:
            graph=csvwtordf_prov(graph, self.api_url, self.csv_url, self.metadata_url)
        return graph.serialize(format=format)

from app import settings

def csvwtordf_prov(graph: Graph, api_url: str, csv_url: str, metadata_url: str) -> dict:
        graph.bind('prov',PROV)
        tables=list(graph[:RDF.type:CSVW.Table])
        print(tables)
        for table in tables:
            api_node=URIRef(api_url)
            graph.add((table,PROV.wasGeneratedBy,api_node))
            graph.add((api_node,RDF.type,PROV.Activity))
            software_node=URIRef("https://github.com/Mat-O-Lab/CSVToCSVW/releases/tag/"+settings.version)
            graph.add((api_node,PROV.wasAssociatedWith,software_node))
            graph.add((software_node,RDF.type,PROV.SoftwareAgent))
            graph.add((software_node,RDFS.label,Literal( settings.app_name+settings.version)))
            graph.add((software_node,PROV.hadPrimarySource,URIRef(settings.source)))
            graph.add((table,PROV.generatedAtTime,Literal(str(datetime.now().isoformat()),datatype=XSD.dateTime)))
            csv_usage=URIRef(csv_url)
            graph.add((csv_usage,RDF.type,PROV.Usage))
            graph.add((csv_usage,PROV.hadRole,CSVW.csvEncodedTabularData))
            graph.add((table,PROV.qualifiedUsage,csv_usage))
            meta_usage=URIRef(metadata_url)
            graph.add((meta_usage,RDF.type,PROV.Usage))
            graph.add((meta_usage,PROV.hadRole,CSVW.tabularMetadata))
            graph.add((table,PROV.qualifiedUsage,meta_usage))
        return graph