import logging
import random
import string
from flask import Flask, request, abort, jsonify, make_response
from flask.ext.sqlalchemy import SQLAlchemy, DeclarativeMeta
import json

import timeseries

logger = logging.getLogger(__name__)


class ProductJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            return obj.to_dict()
        return super(ProductJSONEncoder, self).default(obj)


app = Flask(__name__, static_url_path='/static')  # Create an instance of the Flask web server
app.json_encoder = ProductJSONEncoder

user = 'cs207site'
password = 'cs207isthebest'
host = 'localhost'
port = '5432'
dbname = 'timeseries'
url = 'postgresql://{}:{}@{}:{}/{}'
url = url.format(user, password, host, port, dbname)
app.config['SQLALCHEMY_DATABASE_URI'] = url  # 'sqlite:////tmp/tasks.db' # NEEDS FIXING
db = SQLAlchemy(app)


class TimeseriesEntry(db.Model):
    """A single timeseries dataset in the timeseries database.
        Contains the following columns:
            id - int - The unique identifier of the timeseries (generated by SQL)
            blarg - float - A random metadata value sampled from [0,1]
            level - char - Randomly selected letter between A and F
            mean - float - Average value of the timeseries
            std - float - Standard deviation of the timeseries
            fpath - string - File path to the time series file (NEEDS TO BE REPLACED WITH STORAGE MANAGER)
    """
    __tablename__ = 'timeseries'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    blarg = db.Column(db.Float, nullable=False)
    level = db.Column(db.String(1), nullable=False)
    mean = db.Column(db.Float, nullable=False)
    std = db.Column(db.Float, nullable=False)
    fpath = db.Column(db.String(80), nullable=False)

    def __repr__(self):
        return '<ID %d, blarg %f, level %s>' % (self.id, self.blarg, self.level)

    def to_dict(self):
        return dict(id=self.id, blarg=self.blarg, level=self.level, mean=self.mean, std=self.std, fpath=self.fpath)


def get_floating_range(range_str):
    if "-" not in range_str:
        raise KeyError("Invalid input range: %s" % range_str)
    range_components = range_str.split('-')
    if len(range_components) != 2:
        raise KeyError("Found too many range indications in: %s" % range_str)
    return float(range_components[0]), float(range_components[1])


@app.route('/timeseries', methods=['GET'])
def get_all_metadata():
    """/timeseries GET endpoint
        Defines two API calls:
            * /timeseries GET - Return a JSON containing metadata info from all timeseries
            * /timeseries?request=value(s) GET - Return timeseries that match the request. Valid requests are:
                + blarg_in=lower-upper - Get data with a blarg that falls within the floating point range
                + level_in=X,Y - Get data that contains one of the comma separated letters
                + mean_in=lower-upper - Get data with a mean that falls within the floating point range
                + std_in=lower-upper - Get data with a std that falls within the floating point range
    """
    try:
        if 'blarg_in' in request.args:
            logger.debug("Getting entries by blarg value")
            lower, upper = get_floating_range(request.args.get('blarg_in'))
            results = db.session.query(TimeseriesEntry). \
                filter(TimeseriesEntry.blarg >= lower). \
                filter(TimeseriesEntry.blarg < upper)
        elif 'level_in' in request.args:
            logger.debug("Getting entries by level value")
            levels = request.args.get('mean_in').split(",")
            results = db.session.query(TimeseriesEntry). \
                filter(TimeseriesEntry.level.in_(levels))
        elif 'mean_in' in request.args:
            logger.debug("Getting entries by mean value")
            lower, upper = get_floating_range(request.args.get('mean_in'))
            results = db.session.query(TimeseriesEntry). \
                filter(TimeseriesEntry.mean >= lower). \
                filter(TimeseriesEntry.mean < upper)
        elif 'std_in' in request.args:
            logger.debug("Getting entries by std value")
            lower, upper = get_floating_range(request.args.get('std_in'))
            results = db.session.query(TimeseriesEntry). \
                filter(TimeseriesEntry.std >= lower). \
                filter(TimeseriesEntry.std < upper)
        else:
            logger.info("Getting all TimeseriesEntries")
            results = db.session.query(TimeseriesEntry).all()
        return jsonify(dict(timeseries=results))
    except KeyError as e:
        logger.warning("Invalid timeseries GET request: %s" % str(e))
        abort(400)


def generate_timeseries_from_json(raw_json):
    """Return an ArrayTimeSeries object containing the data in a json file with the following format:
        {
            time_points = [list of strings]
            data_points = [list of strings]
        }
    """
    time_points = [float(x) for x in raw_json["time_points"]]
    data_points = [float(x) for x in raw_json["data_points"]]
    return timeseries.ArrayTimeSeries(time_points, data_points)


def save_timeseries_to_file(ts):
    """Saves an ArrayTimeSeries to a local file in the results folder.
        Each file is given a random name to prevent file conflicts.
        Note: This system needs to be replaced by the storage manager"""
    filename = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(20)) + ".json"
    time_points, data_points = zip(*ts.iteritems())
    data = {
        "time_points": time_points,
        "data_points": data_points
    }
    with open(filename, "w") as f:
        json.dump(data, f)
    return filename


def load_timeseries_from_file(filename):
    """Loads an ArrayTimeSeries from a local file"""
    with open(filename, "r") as f:
        data = json.load(f)
    return generate_timeseries_from_json(data)


@app.route('/timeseries', methods=['POST'])
def create_entry():
    """/timeseries POST endpoint
        Defines the following API call:
            * /timeseries POST - Add a new timeseries to the database with a JSON in the following format:
                {
                    time_points = [list of floats]
                    data_points = [list of floats]
                } # Note: This may be changed. The ID field has been omitted, as the user should not have that
    """
    if not request.json or not "time_points" in request.json or not "data_points" in request.json:
        logger.warning("Invalid POST request to timeseries")
        abort(400)
        return
    logger.debug('Creating TimeseriesEntry')
    try:
        ts = generate_timeseries_from_json(request.json)  # Create actual timeseries object
    except Exception as e:
        logger.warning("Could not create timeseries object with exception: %s" % str(e))
        abort(400)
        return
    mean = ts.mean()  # Get mean and standard deviation from object
    std = ts.std()
    blarg = random.random()
    level = random.choice(["A", "B", "C", "D", "E", "F"])

    # Save to file and get fpath (replace with storage manager)
    fpath = save_timeseries_to_file(ts)

    # Create TimeseriesEntry
    prod = TimeseriesEntry(blarg=blarg, level=level, mean=mean, std=std, fpath=fpath)
    db.session.add(prod)
    db.session.commit()
    result = {
        "time_points": request.json["time_points"],
        "data_points": request.json["data_points"],
        "mean": mean,
        "std": std,
        "blarg": blarg,
        "level": level
    }
    return jsonify(result), 201


@app.route('/timeseries/<int:timeseries_id>', methods=['GET'])
def get_timeseries_by_id(timeseries_id):
    """/timeseries/id GET endpoint
        Defines the following API call:
            * /timeseries/id GET - Return the timeseries and associated metadata as a JSON object
    """
    te = db.session.query(TimeseriesEntry).filter_by(id=timeseries_id).first()
    if te is None:
        logger.warning('Failed to get TimeseriesEntry with id=%s', timeseries_id)
        abort(404)
        return
    logger.debug('Getting TimeseriesEntry with id=%s', timeseries_id)
    ts = load_timeseries_from_file(te.fpath)
    time_points, data_points = zip(*ts.iteritems())
    result = {
        "time_points": time_points,
        "data_points": data_points,
        "mean": te.mean,
        "std": te.std,
        "blarg": te.blarg,
        "level": te.level
    }
    return jsonify(result)


@app.route('/simquery', methods=['GET'])
def get_simquery():
    """/simquery GET endpoint
        Defines the following API call:
            * /simquery/id=x - GET - Returns the top 5 most similar timeseries to the entry indicated by id as
                {
                    similar_ids = [list of 5 ids]
                }
    """
    if 'id' not in request.args:
        logger.warning("ID is required for similarity search")
        abort(400)
    timeseries_id = request.args.get('id')
    te = db.session.query(TimeseriesEntry).filter_by(id=timeseries_id).first()
    if te is None:
        logger.warning('Failed to get TimeseriesEntry with id=%s', timeseries_id)
        abort(404)
        return
    ts = load_timeseries_from_file(te.fpath)
    # NOTE: PLEASE ADD SIMILARITY SEARCH
    sim_ids = [random.randint(0, 10) for _ in range(5)]  # REPLACE THIS
    return jsonify({"similar_ids": sim_ids})


@app.route('/simquery', methods=['POST'])
def post_simquery():
    """/simquery POST endpoint
        Defines the following API call:
            * /simquery - POST - Get similar timeseries to a given timeseries without adding to database. Returns:
                {
                    similar_ids = [list of 5 ids]
                }
    """
    if not request.json or not "time_points" in request.json or not "data_points" in request.json:
        logger.warning("Invalid POST request to simquery")
        abort(400)
        return
    try:
        ts = generate_timeseries_from_json(request.json)  # Create actual timeseries object
    except Exception as e:
        logger.warning("Could not create timeseries object with exception: %s" % str(e))
        abort(400)
        return
    # NOTE: PLEASE ADD SIMILARITY SEARCH
    sim_ids = [random.randint(0, 10) for _ in range(5)]  # REPLACE THIS
    return jsonify({"similar_ids": sim_ids})

@app.route('/')
def root():
    return app.send_static_file('index.html')

@app.route('/main.js')
def main_js():
    return app.send_static_file('main.js')

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    db.create_all()
    app.run(port=8080)
