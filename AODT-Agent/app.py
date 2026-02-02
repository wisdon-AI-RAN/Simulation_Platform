from flask import Flask
from controllers.restart_aodt import aodt_restart_bp
from controllers.test_route import test_bp
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.register_blueprint(aodt_restart_bp)
app.register_blueprint(test_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)