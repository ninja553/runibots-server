from flask import Flask, request, jsonify
import requests
import base64
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# Clave secreta para autorización (reemplaza con una clave segura)
ADMIN_KEY = "tu_clave_secreta_admin"

# URL del webhook de Discord (reemplaza con tu URL)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1366414104171909191/d4McCwAD6pct0DAeF18gNIN6iD6B50tjRtqyQtnsf_l4dTnL_bM9T6EacyS3qDarOrj5"

# Configuración de GitHub (obtenida de variables de entorno)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Formato: "usuario/repositorio"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

# Headers para la API de GitHub
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Nombres de los archivos en el repositorio
HARDWARE_IDS_FILE = "hardware_ids.txt"
AUTHORIZED_IDS_FILE = "authorized_ids.txt"

# Función para leer un archivo desde GitHub
def read_file_from_github(filename):
    url = f"{GITHUB_API_URL}/{filename}"
    response = requests.get(url, headers=GITHUB_HEADERS)
    
    if response.status_code == 200:
        content = response.json()
        # El contenido viene en Base64, lo decodificamos
        file_content = base64.b64decode(content["content"]).decode("utf-8")
        sha = content["sha"]
        return file_content, sha
    elif response.status_code == 404:
        # Si el archivo no existe, lo creamos
        content = "" if filename == HARDWARE_IDS_FILE else "hardware_id,fecha_autorizacion,dias_validez\n"
        write_file_to_github(filename, content, "Initial commit for " + filename)
        return content, None
    else:
        raise Exception(f"Error al leer {filename} desde GitHub: {response.json().get('message')}")

# Función para escribir un archivo en GitHub
def write_file_to_github(filename, content, commit_message, sha=None):
    url = f"{GITHUB_API_URL}/{filename}"
    # Codificar el contenido en Base64
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": commit_message,
        "content": encoded_content
    }
    if sha:
        payload["sha"] = sha  # Necesario para actualizar un archivo existente
    
    response = requests.put(url, headers=GITHUB_HEADERS, json=payload)
    if response.status_code not in [200, 201]:
        raise Exception(f"Error al escribir {filename} en GitHub: {response.json().get('message')}")

@app.route("/submit_hardware_id", methods=["POST"])
def submit_hardware_id():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid JSON format"}), 400

    hardware_id = data.get("hardware_id")
    
    if not hardware_id:
        return jsonify({"status": "error", "message": "hardware_id is required"}), 400
    
    # Leer el contenido actual de hardware_ids.txt desde GitHub
    try:
        file_content, sha = read_file_from_github(HARDWARE_IDS_FILE)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Evitar duplicados
    hardware_ids = set(line.strip() for line in file_content.splitlines() if line.strip())
    if hardware_id in hardware_ids:
        return jsonify({"status": "success", "message": "hardware_id already submitted"}), 200
    
    # Añadir el nuevo hardware_id
    hardware_ids.add(hardware_id)
    new_content = "\n".join(hardware_ids) + "\n"
    
    # Escribir el archivo actualizado en GitHub
    try:
        write_file_to_github(HARDWARE_IDS_FILE, new_content, f"Add hardware_id: {hardware_id}", sha)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Enviar notificación a Discord
    try:
        discord_payload = {
            "content": f"Nuevo hardware_id recibido: `{hardware_id}`"
        }
        requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
    except Exception as e:
        pass  # Ignorar errores de notificación
    
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
    
    # Leer el contenido de authorized_ids.txt desde GitHub
    try:
        file_content, _ = read_file_from_github(AUTHORIZED_IDS_FILE)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Verificar si el hardware_id está autorizado y no ha expirado
    authorized_ids = []
    lines = file_content.splitlines()
    for line in lines[1:]:  # Saltar el encabezado
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
    validity_days = data.get("validity_days", 30)  # Por defecto 30 días
    
    if not hardware_id or not admin_key:
        return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400
    
    if admin_key != ADMIN_KEY:
        return jsonify({"status": "error", "message": "Invalid admin_key"}), 403
    
    # Leer el contenido actual de authorized_ids.txt desde GitHub
    try:
        file_content, sha = read_file_from_github(AUTHORIZED_IDS_FILE)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Actualizar o añadir la autorización
    lines = file_content.splitlines()
    new_lines = [lines[0]]  # Mantener el encabezado
    found = False
    for line in lines[1:]:
        if line.strip() and line.startswith(f"{hardware_id},"):
            found = True
            current_date = datetime.now().strftime("%Y-%m-%d")
            new_lines.append(f"{hardware_id},{current_date},{validity_days}")
        else:
            new_lines.append(line)
    
    if not found:
        current_date = datetime.now().strftime("%Y-%m-%d")
        new_lines.append(f"{hardware_id},{current_date},{validity_days}")
    
    new_content = "\n".join(new_lines) + "\n"
    
    # Escribir el archivo actualizado en GitHub
    try:
        write_file_to_github(AUTHORIZED_IDS_FILE, new_content, f"Authorize hardware_id: {hardware_id}", sha)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Enviar notificación a Discord
    try:
        discord_payload = {
            "content": f"Hardware ID autorizado: `{hardware_id}` por {validity_days} días."
        }
        requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
    except Exception as e:
        pass  # Ignorar errores de notificación
    
    return jsonify({"status": "success", "message": "hardware_id authorized", "validity_days": validity_days}), 200

@app.route("/get_hardware_ids", methods=["GET"])
def get_hardware_ids():
    try:
        file_content, _ = read_file_from_github(HARDWARE_IDS_FILE)
        hardware_ids = [line.strip() for line in file_content.splitlines() if line.strip()]
        return jsonify({"status": "success", "hardware_ids": hardware_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_authorized_ids", methods=["GET"])
def get_authorized_ids():
    try:
        file_content, _ = read_file_from_github(AUTHORIZED_IDS_FILE)
        authorized_ids = []
        lines = file_content.splitlines()
        for line in lines[1:]:  # Saltar el encabezado
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
    
    # Leer el contenido actual de authorized_ids.txt desde GitHub
    try:
        file_content, sha = read_file_from_github(AUTHORIZED_IDS_FILE)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Reescribir excluyendo el hardware_id revocado
    lines = file_content.splitlines()
    new_lines = [lines[0]]  # Mantener el encabezado
    for line in lines[1:]:
        if line.strip() and not line.startswith(f"{hardware_id},"):
            new_lines.append(line)
    
    new_content = "\n".join(new_lines) + "\n"
    
    # Escribir el archivo actualizado en GitHub
    try:
        write_file_to_github(AUTHORIZED_IDS_FILE, new_content, f"Revoke hardware_id: {hardware_id}", sha)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
    # Enviar notificación a Discord
    try:
        discord_payload = {
            "content": f"Autorización revocada para Hardware ID: `{hardware_id}`"
        }
        requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
    except Exception as e:
        pass  # Ignorar errores de notificación
    
    return jsonify({"status": "success", "message": f"hardware_id {hardware_id} revoked"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)