from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# Clave secreta para autorización (reemplaza con una clave segura)
ADMIN_KEY = "tu_clave_secreta_admin"

# URL del webhook de Discord (reemplaza con tu URL)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/tu_webhook_aqui"

# Archivo para almacenar hardware_ids y autorizaciones
HARDWARE_IDS_FILE = "hardware_ids.txt"
AUTHORIZED_IDS_FILE = "authorized_ids.txt"

# Asegurarse de que los archivos existan
if not os.path.exists(HARDWARE_IDS_FILE):
    with open(HARDWARE_IDS_FILE, "w") as f:
        pass

if not os.path.exists(AUTHORIZED_IDS_FILE):
    with open(AUTHORIZED_IDS_FILE, "w") as f:
        f.write("hardware_id,fecha_autorizacion,dias_validez\n")

@app.route("/submit_hardware_id", methods=["POST"])
def submit_hardware_id():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid JSON format"}), 400

    hardware_id = data.get("hardware_id")
    
    if not hardware_id:
        return jsonify({"status": "error", "message": "hardware_id is required"}), 400
    
    # Guardar el hardware_id en el archivo
    with open(HARDWARE_IDS_FILE, "a") as f:
        f.write(hardware_id + "\n")
    
    # Enviar notificación a Discord
    try:
        discord_payload = {
            "content": f"Nuevo hardware_id recibido: `{hardware_id}`"
        }
        requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
    except Exception as e:
        pass  # Ignorar errores de notificación para no afectar la respuesta
    
    return jsonify({"status": "success", "message": "hardware_id submitted"}), 200

@app.route("/verify", methods=["POST"])
def verify():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid JSON format"}), 400

    hardware_id = data.get("hardware_id")
    
    if not hardware_id:
        return jsonify({"status": "error", "message": "hardware_id is required"}), 400
    
    # Verificar si el hardware_id está autorizado y no ha expirado
    authorized_ids = []
    with open(AUTHORIZED_IDS_FILE, "r") as f:
        lines = f.readlines()
        # Saltar la primera línea (encabezado)
        for line in lines[1:]:
            if line.strip():
                parts = line.strip().split(",")
                if len(parts) != 3:
                    continue
                auth_hardware_id, auth_date, validity_days = parts
                if auth_hardware_id == hardware_id:
                    try:
                        auth_date = datetime.strptime(auth_date, "%Y-%m-%d")
                        validity_days = int(validity_days)
                        expiration_date = auth_date + timedelta(days=validity_days)
                        current_date = datetime.now()
                        if current_date <= expiration_date:
                            authorized_ids.append({
                                "hardware_id": auth_hardware_id,
                                "fecha_autorizacion": auth_date.strftime("%Y-%m-%d"),
                                "dias_validez": validity_days,
                                "fecha_expiracion": expiration_date.strftime("%Y-%m-%d")
                            })
                    except ValueError:
                        continue
    
    if authorized_ids:
        return jsonify({"status": "success", "message": "Authorized", "details": authorized_ids[0]}), 200
    else:
        return jsonify({"status": "error", "message": "Not authorized or authorization expired"}), 403

@app.route("/authorize", methods=["POST"])
def authorize():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid JSON format: " + str(e)}), 400

    hardware_id = data.get("hardware_id")
    admin_key = data.get("admin_key")
    validity_days = data.get("validity_days", 30)  # Por defecto 30 días si no se especifica
    
    if not hardware_id or not admin_key:
        return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
    
    if admin_key != ADMIN_KEY:
        return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
    
    # Registrar la autorización con fecha y tiempo de validez
    current_date = datetime.now().strftime("%Y-%m-%d")
    with open(AUTHORIZED_IDS_FILE, "a") as f:
        f.write(f"{hardware_id},{current_date},{validity_days}\n")
    
    return jsonify({"status": "success", "message": "hardware_id authorized", "validity_days": validity_days}), 200

@app.route("/get_hardware_ids", methods=["GET"])
def get_hardware_ids():
    try:
        with open(HARDWARE_IDS_FILE, "r") as f:
            hardware_ids = [line.strip() for line in f if line.strip()]
        return jsonify({"status": "success", "hardware_ids": hardware_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_authorized_ids", methods=["GET"])
def get_authorized_ids():
    try:
        authorized_ids = []
        with open(AUTHORIZED_IDS_FILE, "r") as f:
            lines = f.readlines()
            # Saltar la primera línea (encabezado)
            for line in lines[1:]:
                if line.strip():
                    parts = line.strip().split(",")
                    if len(parts) != 3:
                        continue
                    hardware_id, auth_date, validity_days = parts
                    try:
                        auth_date = datetime.strptime(auth_date, "%Y-%m-%d")
                        validity_days = int(validity_days)
                        expiration_date = auth_date + timedelta(days=validity_days)
                        current_date = datetime.now()
                        status = "active" if current_date <= expiration_date else "expired"
                        authorized_ids.append({
                            "hardware_id": hardware_id,
                            "fecha_autorizacion": auth_date.strftime("%Y-%m-%d"),
                            "dias_validez": validity_days,
                            "fecha_expiracion": expiration_date.strftime("%Y-%m-%d"),
                            "status": status
                        })
                    except ValueError:
                        continue
        return jsonify({"status": "success", "authorized_ids": authorized_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/revoke", methods=["POST"])
def revoke():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid JSON format: " + str(e)}), 400

    hardware_id = data.get("hardware_id")
    admin_key = data.get("admin_key")
    
    if not hardware_id or not admin_key:
        return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
    
    if admin_key != ADMIN_KEY:
        return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
    
    # Leer todas las autorizaciones
    lines = []
    with open(AUTHORIZED_IDS_FILE, "r") as f:
        lines = f.readlines()
    
    # Reescribir el archivo excluyendo el hardware_id revocado
    with open(AUTHORIZED_IDS_FILE, "w") as f:
        f.write(lines[0])  # Mantener el encabezado
        for line in lines[1:]:
            if line.strip() and not line.startswith(f"{hardware_id},"):
                f.write(line)
    
    return jsonify({"status": "success", "message": f"hardware_id {hardware_id} revoked"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)