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

from fastapi import Request, FastAPI, Body, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
#from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

from wtforms import URLField, SelectField, FileField
#from wtforms.validators import DataRequired

from datetime import datetime

import logging

from annotator import CSV_Annotator, TextEncoding
from csvw_parser import CSVWtoRDF

def path2url(path):
    return urlparse(path,scheme='file').geturl()

import settings
setting = settings.Setting()



#flash integration flike flask flash
def flash(request: Request, message: Any, category: str = "info") -> None:
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flashed_messages(request: Request):
    print(request.session)
    return request.session.pop("_messages") if "_messages" in request.session else []

middleware = [
    Middleware(SessionMiddleware, secret_key=os.environ.get('APP_SECRET','1nji79hb10009')),
    Middleware(CSRFProtectMiddleware, csrf_secret='1nji79hb10009'),
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
        schema_extra = {
            "example": {
                "data_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example.csv"
            }
        }

class AnnotateResponse(BaseModel):
    filename:  str = Field('example-metadata.json', title='Resulting File Name', description='Suggested filename of the generated json-ld')
    filedata: dict = Field( title='Generated JSON-LD', description='The generated jdon-ld for the given raw csv file as string in utf-8.')

class RDFRequest(BaseModel):
    metadata_url: AnyUrl = Field('', title='Graph Url', description='Url to csvw metadata to use.')
    csv_url: Optional[AnyUrl] = Field('', title='CSV Url', description='Url to csvw file to use or else the mentioned url in metadata will be used.')
    format: Optional[str] = Field('turtle', title='Serialization Format', description='The format to use to serialize the rdf.')
    as_json: Optional[bool] = Field(False, title='Return JSON response', description='If to return the response as JSON.')

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
async def get_index(request: Request):
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
async def post_index(request: Request):
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
async def annotate(request: Request, annotate: AnnotateRequest) -> dict:
    annotator = CSV_Annotator(annotate.data_url, encoding=annotate.encoding)
    result=annotator.annotate()
    result["filedata"]={**result["filedata"],**annotate_prov(request.url._url)}
    return result

@app.post("/api/annotate_upload",response_model=AnnotateResponse)
async def annotate_upload(request: Request, file: UploadFile = File(...), encoding: TextEncoding=TextEncoding.DETECT) -> dict:
    with open(file.filename, "wb") as f:
        f.write(await file.read())
    annotator = CSV_Annotator("file://"+os.getcwd()+'/'+file.filename, encoding=encoding.value)
    print(annotator)
    result=annotator.annotate()
    result["filedata"]={**result["filedata"],**annotate_prov(request.url._url)}
    #delete the temp csv file
    if os.path.isfile(file.filename):
        os.remove(file.filename)
    return result


@app.post("/api/rdf", response_model=RDFResponse, responses={
        200: {
            "content": {"text/utf-8": {}},
            "description": "Return serialized rdf as file download.",
        }
    })
async def rdf(request: Request, rdfrequest: RDFRequest= Body(
        examples={
            "as download": {
                "summary": "A rdf example, returned as download",
                "description": "Creates rdf from csv file and csvw metadata description.",
                "value": {
                    "metadata_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example-metadata.json",
                    },
            },
            "as json": {
                "summary": "Return directly as json",
                "description": "Creates rdf from csv file and csvw metadata description.",
                "value": {
                    "metadata_url": "https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example-metadata.json",
                    "as_json": True
                    },
            },
        }
    )) -> Response:
    converter=CSVWtoRDF(rdfrequest.metadata_url,rdfrequest.csv_url, request.url._url)
    filename=converter.file_url.rsplit('/',1)[-1]
    headers = {
        'Content-Disposition': 'attachment; filename={}'.format(filename)
    }
    filedata=converter.convert()
    #print(converter.metadata['tables'][0])
    if rdfrequest.as_json:
        return {"filename": filename, "filedata": filedata}
    else:
        return Response(filedata, headers=headers,  media_type='text/utf-8')
    

@app.get("/info", response_model=settings.Setting)
async def info() -> dict:
    return setting

#time http calls
from time import time
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
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


    
