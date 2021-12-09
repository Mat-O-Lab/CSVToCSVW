from annotator import CSV_Annotator

import os
import base64
import zipfile
from io import BytesIO
from flask import Flask, flash, request, redirect, url_for, Response, render_template, send_file, stream_with_context, \
    get_flashed_messages, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
from flask_wtf import FlaskForm
from flask_bootstrap import Bootstrap

from wtforms import URLField, SelectField
from wtforms.validators import DataRequired

from werkzeug.utils import secure_filename
from config import config

UPLOAD_FOLDER = "tmp"
ALLOWED_EXTENSIONS = {'csv', 'rdf', 'txt', 'tra'}

config_name = os.environ.get("APP_MODE") or "development"

app = Flask(__name__)
app.config.from_object(config[config_name])
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

bootstrap = Bootstrap(app)


SWAGGER_URL = "/api/docs"
API_URL = "/static/swagger.json"
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        "app_name": "CSVtoCSVW"
    }
)

app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
separators = ["auto", ";", ",", "\t", "|", "\s+", "\s+|\t+|\s+\t+|\t+\s+"]
encodings = ['auto', 'ISO-8859-1', 'UTF-8', 'ascii', 'latin-1', 'cp273']

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class StartForm(FlaskForm):
    data_url = URLField('URL Meta Data', validators=[DataRequired()], description='Paste URL to a data file, e.g. csv, TRA')
    separator_sel = SelectField('Choose Separator, default: auto detect', choices=separators, description='select a separator for your data manually', default='auto')
    encoding_sel = SelectField('Choose Encoding, default: auto detect', choices=encodings, description='select an encoding for your data manually', default='auto')


@app.route('/', methods=['GET', 'POST'])
def index():
    logo = './static/resources/MatOLab-Logo.svg'
    start_form = StartForm()
    message = ''
    result= ''
    return render_template("index.html", logo=logo, start_form=start_form, message=message, result=result)

@app.route('/create_annotator', methods=['POST'])
def create_annotator():
    logo = './static/resources/MatOLab-Logo.svg'
    start_form = StartForm()
    message = ''
    result= ''

    if start_form.validate_on_submit():

        annotator = CSV_Annotator(separator=start_form.separator_sel.data, encoding=start_form.encoding_sel.data)


        try:
            meta_file_name, result = annotator.process(start_form.data_url.data)
        except (ValueError, TypeError) as error:
            flash(str(error))
        else:
            b64 = base64.b64encode(result.encode())
            payload = b64.decode()

            return render_template("index.html", logo=logo, start_form=start_form, message=message, result=result, payload=payload, filename = meta_file_name)

    return render_template("index.html", logo=logo, start_form=start_form, message=message, result=result)



@app.route('/multinput', methods=['GET', 'POST'])
def multinput():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'files' not in request.files:
            flash('No file part')
            return redirect(request.url)


        files = request.files.getlist("files")

        separator = request.form["separator"]
        encoding = request.form["encoding"]

        # create annotator object for reading files
        annotator = CSV_Annotator(encoding=encoding, separator=separator)

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for file in files:

                if file.filename == '':
                    print("No selected file")
                    flash('No selected file')
                    continue

                if file and allowed_file(file.filename):

                    filename = secure_filename(file.filename)
                    file.filename = filename
                    meta_file_name, result = annotator.process(file)
                    zf.writestr(zinfo_or_arcname=meta_file_name, data=result)

        memory_file.seek(0)
        return send_file(memory_file, attachment_filename='result.zip', as_attachment=True)

    return render_template("index.html")

@app.route("/api", methods=["GET", "POST"])
def api():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'files' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files["file"]

        #separator = request.form["separator"]
        #encoding = request.form["encoding"]

        # create annotator object for reading files
        annotator = CSV_Annotator(encoding='auto', separator='auto')

        meta_file_name, result = annotator.process(file)

        return {"meta_file_name" : meta_file_name, "result" : result}
