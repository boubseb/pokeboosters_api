import logging as lg
from collections import Counter
lg.basicConfig(format='%(levelname)-2s -%(message)s',level=lg.INFO)

from flask import Flask, jsonify, request
from flask_cors import CORS,cross_origin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_jwt_extended import JWTManager
from flask_mail import Mail
import psycopg2
import json

app = Flask(__name__)
CORS(app, resources={r"*": {"origins": "*"}})

app.config['JWT_SECRET_KEY'] = "5?]Pz[w:bV64wx7bH53@e7HHu(X!;4NP"
app.config['MAIL_SERVER'] = 'your_mail_server'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_mail_username'
app.config['MAIL_PASSWORD'] = 'your_mail_password'

db_config = {
    'host': '192.168.1.91',
    'database': 'pokeboosters',
    'user': 'seb',
    'password': 'test',
}

jwt = JWTManager(app)
mail = Mail(app)

def connect_to_db():
    conn = psycopg2.connect(**db_config)
    return conn

# configuration
DEBUG = True
CORS(app, resources={r"/*": {"origins": "*"}})


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    print(data)
    username = data['username']
    email = data['email']
    password = data['password']
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("select * from users where pseudo='"+username+"'")
    user = cur.fetchone()      # Fetch the first result

    if user:
        return jsonify({'message': 'Username or email already in use'}), 400
    else:
      print("No results found.")
      sql = "INSERT INTO users (pseudo,email,password) VALUES (%s, %s, %s);"

      try:
          cur.execute(sql, (username,email,generate_password_hash(password)))
          conn.commit()
          return jsonify({'message': 'User registered successfully'}), 201
      except Exception as e:
          conn.rollback()
          return jsonify({"error": str(e)})
      finally:
          cur.close()
          conn.close()
      

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']
    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("select * from users where pseudo='"+username+"'")

     # Fetch the first result
    user = cur.fetchone()   
    if user and check_password_hash(user[3], password):
        access_token = create_access_token(identity=username)
        return jsonify({'access_token': access_token}), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 401
    

@app.route('/addCardToUserCollection', methods=['PUT'])
@jwt_required()
def addCardToUserCollection():
    cards=request.get_json()
    current_user = get_jwt_identity()
    print(current_user)
    conn = connect_to_db()
    cur = conn.cursor()
    result=[]
    dict_counts = Counter(json.dumps(item, sort_keys=True) for item in cards)
    distinct_cards_with_counts = [{'object': json.loads(item), 'count': count} for item, count in dict_counts.items()]

    for card in distinct_cards_with_counts:
        cur.execute("select * from cards where id='"+card['object']['id']+"'")
        res = cur.fetchone()      # Fetch the first result

        if res is None:
            sql = "INSERT INTO cards (id,data,set_id) VALUES (%s, %s, %s);"
            try:
                print("try None")
                cur.execute(sql, (card['object']['id'],json.dumps(card),card['object']['set']['id']))
                conn.commit()
                result.append({'message': 'card add to cards',"result":201})
            except Exception as e:
                conn.rollback()
                result.append({"error": str(e)})
  

    sql = "INSERT INTO collection (userid,setid,cardid,quantity) VALUES (%s, %s, %s, %s) ON CONFLICT (userid,cardid) DO UPDATE SET quantity=collection.quantity+EXCLUDED.quantity"
    try:
        cur.executemany(sql, [(current_user,card['object']['set']['id'],card['object']['id'],card['count']) for card in distinct_cards_with_counts])
        conn.commit()
        result.append({'message': 'cards add to collection',"result":201})
    except Exception as e:
        conn.rollback()
        result.append({"error": str(e)})
            
    cur.close()
    conn.close()
    return jsonify(result), 200


@app.route('/UserCollection', methods=['GET'])
@jwt_required()
def getUserCollection():
    current_user = get_jwt_identity()
    print(current_user)
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT distinct cards.data FROM collection join cards on cards.id=collection.cardid where collection.userid=%s", (current_user,))
    results = cur.fetchall()    
    cur.close()
    conn.close()
    return jsonify([row[0] for row in results]), 200






