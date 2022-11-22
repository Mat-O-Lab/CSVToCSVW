from distutils.dir_util import copy_tree
from email.policy import default
import os
import base64

from flask import Flask, flash, request, jsonify, render_template
from flask_swagger_ui import get_swaggerui_blueprint
from flask_wtf import FlaskForm
from flask_bootstrap import Bootstrap

from wtforms import URLField, SelectField
from wtforms.validators import DataRequired

import logging

from config import config
from annotator import CSV_Annotator

config_name = os.environ.get("APP_MODE") or "development"

app = Flask(__name__)
app.config.from_object(config[config_name])

bootstrap = Bootstrap(app)

logging.basicConfig(level=logging.DEBUG)

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
separators = ["auto", ";", ",", "\\t", "\\t+",
              "|", ":", "\s+", "\s+|\\t+|\s+\\t+|\\t+\s+"]
encodings = ['auto', 'ISO-8859-1', 'UTF-8', 'ascii', 'latin-1', 'cp273']


class StartForm(FlaskForm):
    data_url = URLField(
        'URL Data File',
        validators=[DataRequired()],
        description='Paste URL to a data file, e.g. csv, TRA',
        default='https://github.com/Mat-O-Lab/CSVToCSVW/raw/main/examples/example.csv'
    )
    separator_sel = SelectField(
        'Choose Data Table Separator, default: auto detect',
        choices=separators,
        description='select a separator for your data table manually',
        default='auto'
        )
    header_separator_sel = SelectField(
        'Choose Additional Header Separator, default: auto detect',
        choices=separators,
        description='select a separator for the additional header manually',
        default='auto'
        )
    encoding_sel = SelectField(
        'Choose Encoding, default: auto detect',
        choices=encodings,
        description='select an encoding for your data manually',
        default='auto'
        )


@app.route('/', methods=['GET', 'POST'])
def index():
    logo = './static/resources/MatOLab-Logo.svg'
    start_form = StartForm()
    message = ''
    result = ''
    return render_template(
        "index.html",
        logo=logo,
        start_form=start_form,
        message=message,
        result=result
        )


@app.route('/create_annotator', methods=['POST'])
def create_annotator():
    logo = './static/resources/MatOLab-Logo.svg'
    start_form = StartForm()
    message = ''
    result = ''

    if start_form.validate_on_submit():
        annotator = CSV_Annotator(
            separator=start_form.separator_sel.data,
            header_separator=start_form.header_separator_sel.data,
            encoding=start_form.encoding_sel.data
        )

        try:
            meta_file_name, result = annotator.process(
                start_form.data_url.data)
        except (ValueError, TypeError) as error:
            flash(str(error))
        else:
            b64 = base64.b64encode(result.encode())
            payload = b64.decode()

            return render_template(
                "index.html",
                logo=logo,
                start_form=start_form,
                message=message,
                result=result,
                payload=payload,
                filename=meta_file_name
            )
    return render_template(
        "index.html",
        logo=logo,
        start_form=start_form,
        message=message,
        result=result
    )


@app.route("/api", methods=["GET", "POST"])
def api():
    if request.method == "POST":
        content = request.get_json()
        if 'encoding' not in content.keys():
            content['encoding']='auto'
        if 'separator' not in content.keys():
            content['separator']='auto'
        if 'header_separator' not in content.keys():
            content['header_separator']='auto'
        annotator = CSV_Annotator(
            encoding=content['encoding'], separator=content['separator'], header_separator=content['header_separator'])
        filename, file_data = annotator.process(content['data_url'])
    return jsonify({"filename": filename, "filedata": file_data})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
