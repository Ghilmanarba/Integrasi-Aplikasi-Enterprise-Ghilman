import os
import jwt
import datetime
from functools import wraps
from flask import Flask, request, jsonify
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)

app.config['JWT_SECRET'] = os.getenv('JWT_SECRET')


users = {
    "ghilman@gmail.com": {
        "password": "102022300435",
        "profile": {
            "name": "ghilman",
            "email": "ghilman@gmail.com"
        }
    }
}

items = [
    {"id": 1, "name": "Laptop", "price": 15000000},
    {"id": 2, "name": "Mouse Gaming", "price": 750000}
]


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
      
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
           
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "token tidak valid/expired/akses tidak sah."}), 401

        try:
            
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
            current_user = users.get(data['sub'])
            if not current_user:
                return jsonify({"error": "user tidak ditemukan"}), 404
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token kadaluarsa"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "token salah"}), 401

        return f(current_user, *args, **kwargs)

    return decorated




@app.route('/auth/login', methods=['POST'])
def login():
    auth = request.get_json()

    if not auth or not auth.get('email') or not auth.get('password'):
        return jsonify({"error": "Missing email or password"}), 400

    user = users.get(auth['email'])

  
    if not user or user['password'] != auth['password']:
        return jsonify({"error": "Invalid credentials"}), 401

   
    payload = {
        'sub': auth['email'],
        'email': auth['email'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    }
    
  
    token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm="HS256")

    return jsonify({"access_token": token})



@app.route('/items', methods=['GET'])
def get_items():
    return jsonify({"items": items})



@app.route('/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    data = request.get_json()
    
   
    if not data or ('name' not in data and 'email' not in data):
        return jsonify({"error": "Request body must contain 'name' or 'email'"}), 400

  
    if 'name' in data:
        current_user['profile']['name'] = data['name']
    if 'email' in data:
        
        current_user['profile']['email'] = data['email']
    
    
    print(f"INFO: Profile for {current_user['profile']['email']} updated.")

    return jsonify({
        "message": "profil berhasil diperbarui",
        "profile": current_user['profile']
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, port=port)