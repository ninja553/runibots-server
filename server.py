from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime, timedelta
import time

app = Flask(__name__)

# Clave secreta para autorización (configura en variables de entorno de Render)
ADMIN_KEY = os.getenv("ADMIN_KEY", "tu_clave_secreta_admin")

# URL del webhook de Discord
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1366414104171909191/d4McCwAD6pct0DAeF18gNIN6iD6B50tjRtqyQtnsf_l4dTnL_bM9T6EacyS3qDarOrj5"

# Archivos para hardware_ids
HARDWARE_IDS_FILE = "hardware_ids.txt"
AUTHORIZED_IDS_FILE = "authorized_ids.txt"

# Asegurarse de que los archivos existan
if not os.path.exists(HARDWARE_IDS_FILE):
    with open(HARDWARE_IDS_FILE, "w") as f:
        pass

if not os.path.exists(AUTHORIZED_IDS_FILE):
    with open(AUTHORIZED_IDS_FILE, "w") as f:
        f.write("hardware_id,fecha_autorizacion,dias_validez\n")

# Diccionario para rastrear actividad e instancias
client_activity = {}
INACTIVITY_THRESHOLD = 840  # 14 minutos en segundos

def send_to_discord(message):
    """Envía un mensaje al webhook de Discord con depuración."""
    try:
        discord_payload = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
        response.raise_for_status()
        print(f"Mensaje enviado a Discord: {message}")
    except Exception as e:
        print(f"Error al enviar mensaje a Discord: {e}")

@app.route("/submit_hardware_id", methods=["POST"])
def submit_hardware_id():
    try:
        data = request.get_json()
        hardware_id = data.get("hardware_id")
        instance_id = data.get("instance_id", "default_instance")
        
        if not hardware_id:
            return jsonify({"status": "error", "message": "hardware_id is required"}), 400
        
        # Guardar el hardware_id en hardware_ids.txt
        with open(HARDWARE_IDS_FILE, "a") as f:
            f.write(hardware_id + "\n")
        
        # Enviar notificación a Discord
        send_to_discord(f"Nuevo hardware_id recibido: `{hardware_id}`, instance_id: `{instance_id}`")
        
        # Registrar actividad
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
        client_activity[hardware_id]["instances"][instance_id] = time.time()
        client_activity[hardware_id]["status"] = "active"
        client_activity[hardware_id]["last_activity"] = time.time()
        
        return jsonify({"status": "success", "message": "hardware_id submitted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/verify", methods=["POST"])
def verify():
    try:
        data = request.get_json()
        hardware_id = data.get("hardware_id")
        instance_id = data.get("instance_id", "default_instance")
        
        if not hardware_id:
            return jsonify({"status": "error", "message": "hardware_id is required"}), 400
        
        # Verificar autorización
        authorized_ids = []
        with open(AUTHORIZED_IDS_FILE, "r") as f:
            lines = f.readlines()
            for line in lines[1:]:  # Saltar encabezado
                if line.strip():
                    parts = line.strip().split(",")
                    if len(parts) == 3:
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
                                    # Actualizar actividad
                                    if hardware_id not in client_activity:
                                        client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
                                    client_activity[hardware_id]["instances"][instance_id] = time.time()
                                    client_activity[hardware_id]["status"] = "active"
                                    client_activity[hardware_id]["last_activity"] = time.time()
                            except ValueError:
                                continue
        
        if authorized_ids:
            return jsonify({"status": "success", "message": "Authorized", "details": authorized_ids[0]}), 200
        else:
            return jsonify({"status": "error", "message": "Not authorized or authorization expired"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/authorize", methods=["POST"])
def authorize():
    try:
        data = request.get_json()
        hardware_id = data.get("hardware_id")
        admin_key = data.get("admin_key")
        validity_days = data.get("validity_days", 30)
        
        if not hardware_id or not admin_key:
            return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
        
        if admin_key != ADMIN_KEY:
            return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        with open(AUTHORIZED_IDS_FILE, "a") as f:
            f.write(f"{hardware_id},{current_date},{validity_days}\n")
        
        send_to_discord(f"Hardware_id autorizado: `{hardware_id}`, válidez: {validity_days} días")
        return jsonify({"status": "success", "message": "hardware_id authorized", "validity_days": validity_days}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
            for line in lines[1:]:  # Saltar encabezado
                if line.strip():
                    parts = line.strip().split(",")
                    if len(parts) == 3:
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
        hardware_id = data.get("hardware_id")
        admin_key = data.get("admin_key")
        
        if not hardware_id or not admin_key:
            return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
        
        if admin_key != ADMIN_KEY:
            return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
        
        lines = []
        with open(AUTHORIZED_IDS_FILE, "r") as f:
            lines = f.readlines()
        
        with open(AUTHORIZED_IDS_FILE, "w") as f:
            f.write(lines[0])  # Mantener encabezado
            for line in lines[1:]:
                if line.strip() and not line.startswith(f"{hardware_id},"):
                    f.write(line)
        
        send_to_discord(f"Hardware_id revocado: `{hardware_id}`")
        return jsonify({"status": "success", "message": f"hardware_id {hardware_id} revoked"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/report_activity", methods=["POST"])
def report_activity():
    try:
        data = request.get_json()
        hardware_id = data.get("hardware_id")
        instance_id = data.get("instance_id", "default_instance")
        status = data.get("status")
        
        if not hardware_id or not status:
            return jsonify({"status": "error", "message": "hardware_id and status are required"}), 400
        
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
        
        if status == "active":
            client_activity[hardware_id]["instances"][instance_id] = time.time()
            client_activity[hardware_id]["status"] = "active"
            client_activity[hardware_id]["last_activity"] = time.time()
        elif status == "inactive":
            if instance_id in client_activity[hardware_id]["instances"]:
                del client_activity[hardware_id]["instances"][instance_id]
            if not client_activity[hardware_id]["instances"]:
                client_activity[hardware_id]["status"] = "inactive"
        
        return jsonify({"status": "success", "message": "Activity reported"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/active_clients", methods=["GET"])
def active_clients():
    current_time = time.time()
    clients = []
    for hardware_id, info in client_activity.items():
        if (current_time - info["last_activity"]) > INACTIVITY_THRESHOLD:
            info["status"] = "inactive"
            info["instances"] = {}
        
        clients.append({
            "hardware_id": hardware_id,
            "status": info["status"],
            "last_activity": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info["last_activity"])),
            "instance_count": len(info["instances"]),
            "instances": list(info["instances"].keys())
        })
    
    return jsonify({"status": "success", "clients": clients}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
