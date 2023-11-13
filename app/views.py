import logging as lg
from collections import Counter
lg.basicConfig(format='%(levelname)-2s -%(message)s',level=lg.INFO)

from flask import Flask, jsonify, request
from flask_cors import CORS,cross_origin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_socketio import SocketIO, emit
from flask_jwt_extended import JWTManager
from flask_mail import Mail
import psycopg2
import json
import requests
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app, resources={r"*": {"origins": "*"}})

app.config['JWT_SECRET_KEY'] = "5?]Pz[w:bV64wx7bH53@e7HHu(X!;4NP"
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
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
      sql = "INSERT INTO users (pseudo,email,password,pokedollars) VALUES (%s, %s, %s,%s);"

      try:
          cur.execute(sql, (username,email,generate_password_hash(password),10000    ))
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
        cur.execute("Select pokedollars from users where pseudo='"+username+"'")
        usermoney = cur.fetchone()   
        socketio.emit('value_updated', {'money':float(usermoney[0]) ,'user':username}) 
        return jsonify({'access_token': access_token,'money':float(usermoney[0])}), 200
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
                cur.execute(sql, (card['object']['id'],json.dumps(card['object']),card['object']['set']['id']))
                conn.commit()
                result.append({'message': 'card add to cards',"result":201})
            except Exception as e:
                conn.rollback()
                result.append({"error": str(e)})
  

    sql = "INSERT INTO collection (userid,setid,cardid,quantity) VALUES (%s, %s, %s, %s) ON CONFLICT (userid,cardid) DO UPDATE SET quantity=(collection.quantity+EXCLUDED.quantity)"
    try:
        cur.executemany(sql, ((current_user,card['object']['set']['id'],card['object']['id'],card['count']) for card in distinct_cards_with_counts))
        print(cur.statusmessage)
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
    cur.execute("SELECT json_build_object('object',cards.data,'count',collection.quantity) FROM collection join cards on cards.id=collection.cardid where collection.userid=%s", (current_user,))
    results = cur.fetchall()    
    cur.close()
    conn.close()
    return jsonify([row[0] for row in results]), 200


@app.route('/buyBoosters', methods=['POST'])
@jwt_required()
def buyBoosters():
    current_user = get_jwt_identity()
    print(current_user)
    data=request.get_json()
    amount=data['money']
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("Select pokedollars from users where pseudo='"+current_user+"'")
    usermoney = float(cur.fetchone()[0]) 
    if(amount<usermoney):
        cur.execute("UPDATE users SET pokedollars= %s where pseudo=%s ",(usermoney-amount,current_user,))
        conn.commit()
        socketio.emit('value_updated', {'money': usermoney-amount,'user':current_user})
        print('here')
        return jsonify({'money':'true'}), 200
    else:
        return  jsonify({'money':'false'}), 200



@app.route('/getUserData', methods=['GET'])
@jwt_required()
def getUserData():
    current_user = get_jwt_identity()
    print(current_user)
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users where pseudo=%s", (current_user,))
    results = cur.fetchone()    
    cur.close()
    conn.close()
    return jsonify({'money':float(results[5]),'user':results[1]}), 200


@app.route('/scrapSetsAndCards', methods=['GET'])
def scrapp():
    conn = connect_to_db()
    cur = conn.cursor()

    headers = {'X-Api-Key': '6ef86c9f-633b-4411-a6cd-1d8b01533a46',}
    datasets = requests.get('https://api.pokemontcg.io/v2/sets', headers=headers).json()['data']
    sql = "INSERT INTO sets (id,total_cards,data) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET total_cards=sets.total_cards,data=sets.data"
    filter=['basep', 'si1', 'np', 'dpp', 'ru1', 'hsp', 'bwp', 'mcd11', 'mcd12', 'xyp', 'xy0', 'mcd16', 'smp', 'mcd19', 'swshp', 'mcd14', 'mcd15', 'mcd18', 'mcd17', 'mcd21', 'bp', 'fut20', 'tk1a', 'tk1b', 'tk2a', 'tk2b', 'mcd22', 'svp', 'sve']

    cur.executemany(sql,((dataset['id'],dataset['total'],json.dumps(dataset))  for dataset in datasets if dataset['id'] not in filter))
    conn.commit()
    for set in datasets:
        print(set['id'])
        if(set['id']not in filter):
            cards=requests.get('https://api.pokemontcg.io/v2/cards?q=set.id:'+set['id'], headers=headers).json()['data']
            sql = "INSERT INTO cards (id,data,set_id) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET data=cards.data,set_id=cards.set_id"
            cur.executemany(sql,((card['id'],json.dumps(card),card['set']['id']) for card in cards))
            conn.commit()
    cur.close()
    conn.close()
    return jsonify({'money':'success'}), 200







