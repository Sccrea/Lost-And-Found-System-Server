from flask import Flask, jsonify, send_from_directory, send_file
import sqlite3
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lost_and_found.db")

@app.route('/')
def index():
    return send_file("webUI0.02.html")

@app.route('/get_data')
def get_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_name = tables[0][0]

        cursor.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        data = []
        for row in rows:
            data.append(dict(zip(columns, row)))

        conn.close()
        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/images/<filename>')
def get_image(filename):
    return send_from_directory("images", filename)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
