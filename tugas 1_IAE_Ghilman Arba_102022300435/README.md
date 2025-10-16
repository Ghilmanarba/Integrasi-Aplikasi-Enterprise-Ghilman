# Aplikasi Flask dengan JWT
Kelompok 
Ghilman arba 102022300435
Naufal dzaki Akhdani Mohy 102022300381
Cipta Fadhil Alfawwaz 102022300250
Dwi Kurniawan 102022300183
## 1. Setup Environment & Menjalankan Server
```bash
pip install Flask PyJWT python-dotenv
python app.py
```

## 2. Variabel Environment (.env)
```
JWT_SECRET=your_secret_key
PORT=5000
```

## 3. Daftar Endpoint & Skema Ringkas

| Method | Endpoint       | Deskripsi                    |
|--------|---------------|------------------------------|
| POST   | /auth/login   | Login, mendapatkan JWT Token |
| GET    | /items        | Mendapatkan daftar item (Auth) |
| PUT    | /profile      | Update profil pengguna (Auth) |

### Contoh Request & Response

**POST /auth/login**
```json
{
  "email": "user@example.com",
  "password": "password"
}
```
**Response:**
```json
{
  "token": "JWT_TOKEN"
}
```

**GET /items** (Header harus berisi token)
```
Authorization: Bearer <JWT_TOKEN>
```

**PUT /profile**
```json
{
  "name": "Nama Baru",
  "email": "email@baru.com"
}
```

## 4. Contoh cURL

### Login
```bash
curl -X POST http://localhost:5000/auth/login   -H "Content-Type: application/json"   -d '{"email":"user@example.com","password":"password"}'
```

### Get Items
```bash
curl http://localhost:5000/items   -H "Authorization: Bearer <JWT_TOKEN>"
```

### Update Profile
```bash
curl -X PUT http://localhost:5000/profile   -H "Content-Type: application/json"   -H "Authorization: Bearer <JWT_TOKEN>"   -d '{"name":"Nama Baru"}'
```

## 5. Catatan / Asumsi
- Token JWT wajib disertakan untuk endpoint yang membutuhkan autentikasi.
- Data disimpan sementara (in-memory), tidak menggunakan database.
