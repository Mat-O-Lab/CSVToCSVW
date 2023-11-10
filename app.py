# app.py
import os
import base64
from urllib.parse import urlparse

import uvicorn
from starlette_wtf import StarletteForm, CSRFProtectMiddleware, csrf_protect
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse
#from starlette.middleware.cors import CORSMiddleware
import fastapi
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Any, Union
import json

from pydantic import BaseModel, AnyUrl, Field, FileUrl

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
#from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from wtforms import URLField, SelectField, FileField

from datetime import datetime

import logging

from annotator import CSV_Annotator, TextEncoding
from csvw_parser import CSVWtoRDF
from io import BytesIO

def path2url(path):
    return urlparse(path,scheme='file').geturl()

import settings
setting = settings.Setting()

from enum import Enum


class ReturnType(str, Enum):
    jsonld="json-ld"
    n3="n3"
    #nquads="nquads" #only makes sense for context-aware stores
    nt="nt"
    hext="hext"
    #prettyxml="pretty-xml" #only makes sense for context-aware stores
    trig="trig"
    #trix="trix" #only makes sense for context-aware stores
    turtle="turtle"
    longturtle="longturtle"
    xml="xml"



#flash integration flike flask flash
def flash(request: fastapi.Request, message: Any, category: str = "info") -> None:
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flashed_messages(request: fastapi.Request):
    return request.session.pop("_messages") if "_messages" in request.session else []

middleware = [
    Middleware(SessionMiddleware, secret_key=os.environ.get('APP_SECRET','changemeNOW')),
    Middleware(CSRFProtectMiddleware, csrf_secret=os.environ.get('APP_SECRET','changemeNOW')),
    Middleware(CORSMiddleware, 
            allow_origins=["*"], # Allows all origins
            allow_methods=["*"], # Allows all methods
            allow_headers=["*"] # Allows all headers
            ),
    Middleware(uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware, trusted_hosts="*")
    ]
app = fastapi.FastAPI(
    title="CSVtoCSVW",
    description="Generates JSON-LD for various types of CSVs, it adopts the Vocabulary provided by w3c at CSVW to describe structure and information within. Also uses QUDT units ontology to lookup and describe units.",
    version=setting.version,
    contact={"name": "Thomas Hanke, Mat-O-Lab", "url": "https://github.com/Mat-O-Lab", "email": setting.admin_email},
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    openapi_url=setting.openapi_url,
    docs_url=setting.docs_url,
    redoc_url=None,
    swagger_ui_parameters= {'syntaxHighlight': False},
    middleware=middleware
)


app.mount("/static/", StaticFiles(directory='static', html=True), name="static")
templates= Jinja2Templates(directory="templates")
templates.env.globals['get_flashed_messages'] = get_flashed_messages


logging.basicConfig(level=logging.DEBUG)

class AnnotateRequest(BaseModel):
    data_url: Union[AnyUrl, FileUrl] = Field('', title='Raw CSV Url', description='Url to raw csv')
    encoding: Optional[TextEncoding] = Field('auto', title='Encoding', description='Encoding of the file',omit_default=True)
    class Config:
        json_schema_extra = {
            "example": {
                "data_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example.csv"
            }
        }

class AnnotateResponse(BaseModel):
    filename:  str = Field('example-metadata.json', title='Resulting File Name', description='Suggested filename of the generated json-ld')
    filedata: dict = Field( title='Generated JSON-LD', description='The generated jdon-ld for the given raw csv file as string in utf-8.')

class RDFRequest(BaseModel):
    metadata_url: Union[AnyUrl, FileUrl] = Field('', title='Graph Url', description='Url to csvw metadata to use.')
    csv_url: Optional[Union[AnyUrl, FileUrl]] = Field(None, title='CSV Url', description='Url to csvw file to use or else the mentioned url in metadata will be used.')
    format: Optional[ReturnType] = Field(ReturnType.jsonld, title='Serialization Format', description='The format to use to serialize the rdf.')
    class Config:
        json_schema_extra = {
            "examples": [
                {
                        "metadata_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example2-metadata.json",
                        "format": "json-ld"
                },
                {
                        "metadata_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example2-metadata.json",
                        "csv_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example2.csv",
                        "format": "turtle"
                },
            ]
        }
class RDFResponse(BaseModel):
    filename:  str = Field('example.ttl', title='Resulting File Name', description='Suggested filename of the generated rdf.')
    filedata: str = Field( title='Generated RDF', description='The generated rdf for the given meta data file as string in utf-8.')

class StartFormUri(StarletteForm):
    data_url = URLField(
        'URL Data File',
        #validators=[DataRequired()],
        description='Paste URL to a data file, e.g. csv, TRA',
        #validators=[DataRequired(message='Either URL to data file or file upload is required.')],
        render_kw={"class":"form-control", "placeholder": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example.csv"},
    )
    file=FileField(
        'Upload CSV File',
        description='Upload your CSV File here.',
        render_kw={"class":"form-control", "placeholder": "Your CSV File"},
    )
    encoding = SelectField(
        'Choose Encoding, default: auto detect',
        choices= [(encoding.value, encoding.name.capitalize()) for encoding in TextEncoding],
        render_kw={"class":"form-control"},
        description='select an encoding for your data manually',
        default='auto'
        )



@app.get('/', response_class=HTMLResponse, include_in_schema=False)
@csrf_protect
async def get_index(request: fastapi.Request):
    """GET /: form handler
    """
    template="index.html"
    form = await StartFormUri.from_formdata(request)
    return templates.TemplateResponse(template, {"request": request,
        "form": form,
        "result": ''
        }
    )


@app.post('/', response_class=HTMLResponse, include_in_schema=False)
@csrf_protect
async def post_index(request: fastapi.Request):
    """POST /: form handler
    """
    template="index.html"
    form = await StartFormUri.from_formdata(request)
    result = ''
    filename = ''
    payload= ''
    if not (form.data_url.data or form.file.data.filename):
        msg='URL Data File empty: using placeholder value for demonstration.'
        logging.debug('URL Data File empty: using placeholder value for demonstration.')
        form.data_url.data=form.data_url.render_kw['placeholder']
        flash(request,msg,'info')
    if await form.validate_on_submit():
        if form.file.data.filename:
            with open(form.file.data.filename, mode="wb") as f:
                f.write(await form.file.data.read())
                file_path=os.path.realpath(f.name)
                data_url=path2url(file_path)
        elif form.data_url.data:
            data_url=form.data_url.data
        result= await annotate(request=request,annotate=AnnotateRequest(data_url= data_url, encoding=form.data['encoding']))
        filename=result["filename"]
        result=json.dumps(result["filedata"],indent=4)
        b64 = base64.b64encode(result.encode())
        payload = b64.decode()
        #remove temp file
        if form.file.data.filename:
            os.remove(file_path)
    # return response
    return templates.TemplateResponse(template, {"request": request,
        "form": form,
        "result": result,
        "filename": filename,
        "payload": payload
        }
    )

def annotate_prov(api_url: str) -> dict:
        return {
            "prov:wasGeneratedBy": {
                "@id": api_url,
                "@type": "prov:Activity",
                "prov:wasAssociatedWith":  {
                    "@id": "https://github.com/Mat-O-Lab/CSVToCSVW/releases/tag/"+setting.version,
                    "rdfs:label": setting.app_name+setting.version,
                    "prov:hadPrimarySource": setting.source,
                    "@type": "prov:SoftwareAgent"
                }
            },
            "prov:generatedAtTime": {
                    "@value": str(datetime.now().isoformat()),
                    "@type": "xsd:dateTime"
                }
            }

@app.post("/api/annotate",response_model=AnnotateResponse)
async def annotate(request: fastapi.Request, annotate: AnnotateRequest) -> dict:
    annotator = CSV_Annotator(annotate.data_url, encoding=annotate.encoding)
    result=annotator.annotate()
    result["filedata"]={**result["filedata"],**annotate_prov(request.url._url)}
    return result

@app.post("/api/annotate_upload",response_model=AnnotateResponse)
async def annotate_upload(request: fastapi.Request, file: fastapi.UploadFile = fastapi.File(...), encoding: TextEncoding=TextEncoding.DETECT) -> dict:
    with open(file.filename, "wb") as f:
        f.write(await file.read())
    annotator = CSV_Annotator("file://"+os.getcwd()+'/'+file.filename, encoding=encoding.value)
    result=annotator.annotate()
    result["filedata"]={**result["filedata"],**annotate_prov(request.url._url)}
    #delete the temp csv file
    if os.path.isfile(file.filename):
        os.remove(file.filename)
    return result


@app.post("/api/rdf")
async def rdf(request: fastapi.Request, rdfrequest: RDFRequest) -> StreamingResponse:
    authorization=request.headers.get('Authorization',None)
    converter=CSVWtoRDF(rdfrequest.metadata_url,rdfrequest.csv_url, request.url._url,authorization=authorization)
    filedata=converter.convert(rdfrequest.format.value)
    data_bytes=BytesIO(filedata.encode())
    filename=converter.filename
    headers = {
        'Content-Disposition': 'attachment; filename={}'.format(filename),
        'Access-Control-Expose-Headers': 'Content-Disposition'
    }
    if rdfrequest.format==ReturnType.jsonld:
        media_type='application/json'
    elif rdfrequest.format==ReturnType.xml:
        media_type='application/xml'
    elif rdfrequest.format in [ReturnType.turtle, ReturnType.longturtle]:
        media_type='text/turtle'
    else:
        media_type='text/utf-8'
    return StreamingResponse(content=data_bytes, media_type=media_type, headers=headers)

    

@app.get("/info", response_model=settings.Setting)
async def info() -> dict:
    return setting

#time http calls
from time import time
@app.middleware("http")
async def add_process_time_header(request: fastapi.Request, call_next):
    start_time = time()
    response = await call_next(request)
    process_time = time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app_mode=os.environ.get("APP_MODE") or 'production'
    if app_mode=='development':
        reload=True
        access_log=True
    else:
        reload=False
        access_log=False
        "--workers", "6","--proxy-headers"
    uvicorn.run("app:app",host="0.0.0.0",port=port, reload=reload, access_log=access_log)


    
