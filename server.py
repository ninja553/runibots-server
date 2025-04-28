from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Archivo para almacenar los hardware_id
HARDWARE_IDS_FILE = "hardware_ids.txt"

# Clave secreta para autorizar hardware_id (cámbiala por una clave segura)
ADMIN_KEY = "tu_clave_secreta_admin"

# Asegúrate de que el archivo hardware_ids.txt exista
if not os.path.exists(HARDWARE_IDS_FILE):
    with open(HARDWARE_IDS_FILE, "w") as f:
        pass

# Leer hardware_id autorizados desde el archivo
def read_authorized_hardware_ids():
    authorized_ids = set()
    try:
        with open(HARDWARE_IDS_FILE, "r") as f:
            for line in f:
                hardware_id = line.strip()
                if hardware_id:
                    authorized_ids.add(hardware_id)
    except Exception as e:
        print(f"Error al leer hardware_ids.txt: {e}")
    return authorized_ids

# Añadir un hardware_id al archivo
def add_hardware_id(hardware_id):
    try:
        with open(HARDWARE_IDS_FILE, "a") as f:
            f.write(hardware_id + "\n")
    except Exception as e:
        print(f"Error al escribir en hardware_ids.txt: {e}")

@app.route("/submit_hardware_id", methods=["POST"])
def submit_hardware_id():
    data = request.get_json()
    if not data or "hardware_id" not in data:
        return jsonify({"status": "error", "message": "hardware_id es requerido"}), 400

    hardware_id = data["hardware_id"]
    
    # Leer hardware_id existentes
    existing_ids = set()
    try:
        with open(HARDWARE_IDS_FILE, "r") as f:
            existing_ids = set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        pass

    # Añadir el hardware_id si no existe
    if hardware_id not in existing_ids:
        add_hardware_id(hardware_id)
        return jsonify({"status": "success", "message": "Hardware ID recibido y almacenado."})
    else:
        return jsonify({"status": "success", "message": "Hardware ID ya estaba registrado."})

@app.route("/verify", methods=["POST"])
def verify_hardware_id():
    data = request.get_json()
    if not data or "hardware_id" not in data:
        return jsonify({"status": "error", "message": "hardware_id es requerido"}), 400

    hardware_id = data["hardware_id"]
    authorized_ids = read_authorized_hardware_ids()
    
    if hardware_id in authorized_ids:
        return jsonify({"status": "success", "message": "Autorizado"})
    else:
        return jsonify({"status": "error", "message": "No autorizado"})

@app.route("/authorize", methods=["POST"])
def authorize_hardware_id():
    data = request.get_json()
    if not data or "hardware_id" not in data or "admin_key" not in data:
        return jsonify({"status": "error", "message": "hardware_id y admin_key son requeridos"}), 400

    if data["admin_key"] != ADMIN_KEY:
        return jsonify({"status": "error", "message": "Clave de administrador incorrecta"}), 403

    hardware_id = data["hardware_id"]
    authorized_ids = read_authorized_hardware_ids()
    
    if hardware_id not in authorized_ids:
        add_hardware_id(hardware_id)
        return jsonify({"status": "success", "message": f"Hardware ID {hardware_id} autorizado exitosamente."})
    else:
        return jsonify({"status": "success", "message": f"Hardware ID {hardware_id} ya estaba autorizado."})

if __name__ == "__main__":
    # Render asigna un puerto dinámico a través de la variable de entorno PORT
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)