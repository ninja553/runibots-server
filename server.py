from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Clave secreta para autorización (reemplaza con una clave segura)
ADMIN_KEY = "tu_clave_secreta_admin"

# Archivo para almacenar hardware_ids
HARDWARE_IDS_FILE = "hardware_ids.txt"
AUTHORIZED_IDS_FILE = "authorized_ids.txt"

# Asegurarse de que los archivos existan
if not os.path.exists(HARDWARE_IDS_FILE):
    with open(HARDWARE_IDS_FILE, "w") as f:
        pass

if not os.path.exists(AUTHORIZED_IDS_FILE):
    with open(AUTHORIZED_IDS_FILE, "w") as f:
        pass

@app.route("/submit_hardware_id", methods=["POST"])
def submit_hardware_id():
    data = request.get_json()
    hardware_id = data.get("hardware_id")
    
    if not hardware_id:
        return jsonify({"status": "error", "message": "hardware_id is required"}), 400
    
    # Guardar el hardware_id en el archivo
    with open(HARDWARE_IDS_FILE, "a") as f:
        f.write(hardware_id + "\n")
    
    return jsonify({"status": "success", "message": "hardware_id submitted"}), 200

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()
    hardware_id = data.get("hardware_id")
    
    if not hardware_id:
        return jsonify({"status": "error", "message": "hardware_id is required"}), 400
    
    # Verificar si el hardware_id está autorizado
    with open(AUTHORIZED_IDS_FILE, "r") as f:
        authorized_ids = f.read().splitlines()
    
    if hardware_id in authorized_ids:
        return jsonify({"status": "success", "message": "Authorized"}), 200
    else:
        return jsonify({"status": "error", "message": "Not authorized"}), 403

@app.route("/authorize", methods=["POST"])
def authorize():
    data = request.get_json()
    hardware_id = data.get("hardware_id")
    admin_key = data.get("admin_key")
    
    if not hardware_id or not admin_key:
        return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
    
    if admin_key != ADMIN_KEY:
        return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
    
    # Autorizar el hardware_id
    with open(AUTHORIZED_IDS_FILE, "a") as f:
        f.write(hardware_id + "\n")
    
    return jsonify({"status": "success", "message": "hardware_id authorized"}), 200

@app.route("/get_hardware_ids", methods=["GET"])
def get_hardware_ids():
    try:
        with open(HARDWARE_IDS_FILE, "r") as f:
            hardware_ids = f.read().splitlines()
        return jsonify({"status": "success", "hardware_ids": hardware_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)