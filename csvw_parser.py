
from typing import Tuple, List
from collections import OrderedDict
import pandas as pd
from rdflib import BNode, URIRef, Literal, Graph
from rdflib.collection import Collection
from rdflib.util import guess_format
from rdflib.namespace import CSVW, RDF, XSD, PROV, RDFS
from datetime import datetime
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
import io


def get_columns_from_schema(schema: URIRef ,graph: Graph)->OrderedDict:
    column_collection_node=next(graph[ schema : CSVW.column : ],None)
    #collection must be queried in another way
    column_collection=Collection(graph,column_collection_node)
    columns=list(column_collection)
    return OrderedDict([ (column,{ k: v for (k,v) in graph[column:]}) for column in columns])
                

def parse_csv_from_url_to_list(csv_url, num_cols: int, delimiter: str=',', skiprows:int =0, num_header_rows: int=2, encoding: str='utf-8') -> List[List]:
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
    print(delimiter,num_header_rows+skiprows)
    table_data = pd.read_csv(file_string, 
                            header= None,
                            sep=delimiter,
                            usecols=range(num_cols),
                            skiprows=num_header_rows+skiprows,
                            encoding=encoding,
                            skip_blank_lines=False,
                            #on_bad_lines=test_bad_line,    
                            engine='python')
    #remove data after blank line
    blank_df = table_data.loc[table_data.isnull().all(1)]
    if len(blank_df) > 0:
        first_blank_index = blank_df.index[0]
        table_data = table_data[:first_blank_index]
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
        filename = unquote(uri_parsed.path).rsplit('/download/upload')[0].split('/')[-1]
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
    print(parsed_url)
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
        self.metagraph=parse_graph(metadata_url,Graph(base=self.metadata_url),format=metaformat)
        self.metagraph.serialize('test.ttl',format='turtle')
        self.meta_root, url=list(self.metagraph[:CSVW.url])[0]
        #print('meta_root: '+self.meta_root)
        #print('csv_url: '+url)
        self.graph=Graph()
        self.base_url="{}/".format(str(self.meta_root).rsplit('/download/upload')[0].rsplit('/',1)[0])
        parsed_url=urlparse(url)
        if parsed_url.scheme in ['https', 'http', 'file']:
            self.csv_url=url
        else:
            self.csv_url=self.base_url+url
        # replace if set in request
        if csv_url:
            self.csv_url=csv_url
        print(self.metadata_url,self.csv_url)
        self.file_url=self.csv_url.rsplit('/download/upload')[0].rsplit('.',1)[0]+".ttl"
        self.tables={table_node: {} for file, table_node in self.metagraph[: CSVW.table: ]}
        print('tables: {}'.format(self.tables))
        self.table_data=list()
        if self.tables:
            for key, data in self.tables.items():
                dialect=next(self.metagraph[key : CSVW.dialect],None)
                data['dialect']={k: v.value for (k,v) in self.metagraph[dialect:]}
                #print(data['dialect'])
                data['schema']=next(self.metagraph[ key: CSVW.tableSchema: ],None)
                data['columns']=get_columns_from_schema(data['schema'],self.metagraph)
                print(data['columns'])
                # get table form csv_url
                if data['schema']:
                    data['about_url']=next(self.metagraph[data['schema'] : CSVW.aboutUrl],None)
                    #print(data['dialect'])
                    print("skipRows: {} headerRowCount: {}".format(data['dialect'][CSVW.skipRows],data['dialect'][CSVW.headerRowCount]))
                    data['lines'] = parse_csv_from_url_to_list(
                        self.csv_url,
                        delimiter=data['dialect'][CSVW.delimiter],
                        skiprows=data['dialect'][CSVW.skipRows],
                        #always on column less, index is created after reading
                        num_cols=len(data['columns'].keys())-1,
                        num_header_rows=data['dialect'][CSVW.headerRowCount],
                        encoding=data['dialect'][CSVW.encoding],
                        )
    def convert_tables(self) -> Graph:
        g=Graph()
        g.bind("csvw", CSVW)
        table_group=BNode()
        g.add((table_group,RDF.type,CSVW.TableGroup))
        table=BNode()
        for key, data in self.tables.items():
            print("table: {}, about_url: {}".format(key,data['about_url']))
            g.add((table_group,CSVW.table, key))
            g.add((table,RDF.type,CSVW.Table))
            if data['about_url']:
                row_uri=data['about_url']
            else:
                row_uri='#gid-{GID}'
            columns=list(data['columns'].items())
            for index,row in enumerate(data['lines']):
                #print(index, row)
                row_node=BNode()
                value_node=URIRef(row_uri.format(GID=index))
                g.add((table,CSVW.row,row_node))
                g.add((row_node, RDF.type, CSVW.Row))
                g.add((row_node, CSVW.describes, value_node))
                row_num=index+data['dialect'][CSVW.skipRows]+data['dialect'][CSVW.headerRowCount]
                g.add((row_node, CSVW.url, URIRef('{}/row={}'.format(self.csv_url,row_num))))
                for cell_index, cell in enumerate(row):
                    #print(self.columns[cell_index])
                    column_data=columns[cell_index][1]
                    format=column_data.get('format', XSD.string)
                    if column_data[CSVW.name]==Literal('GID'):
                        continue
                    else:
                        # if isinstance(column,URIRef) and str(self.meta_root)!='file:///src/': #has proper uri
                        #     g.add((value_node, column, Literal(cell)))
                        if CSVW.aboutUrl in column_data.keys():
                            aboutUrl=column_data[CSVW.aboutUrl]
                            g.add((value_node, URIRef(aboutUrl.format(GID=index)), Literal(cell, datatype=format)))
                        else:
                            url=column_data[CSVW.name]
                            g.add((value_node, URIRef("{}/{}".format(self.metadata_url.rsplit('/download/upload')[0],url)), Literal(cell, datatype=format)))
        return g
        #self.atdm, self.metadata =converter.convert_to_atdm('standard')
    def convert(self,format: str='turtle') -> str:
        graph=self.convert_tables()
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