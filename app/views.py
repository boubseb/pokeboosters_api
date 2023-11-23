import logging as lg
from collections import Counter
lg.basicConfig(format='%(levelname)-2s -%(message)s',level=lg.INFO)
from flask import Flask, jsonify, request,session
from flask_cors import CORS,cross_origin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity,JWTManager
from flask_socketio import SocketIO, emit
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

connected_users = {}

jwt = JWTManager(app)
mail = Mail(app)

def connect_to_db():
    conn = psycopg2.connect(**db_config)
    return conn

# configuration
DEBUG = True
CORS(app, resources={r"/*": {"origins": "*"}})


@socketio.on('user_connect')
@jwt_required()
def handle_connection():
    current_user= get_jwt_identity()
    connected_users[current_user.strip()] = request.sid
    print("New user sign in!\nThe users are: ",current_user)

      

@app.route('/login', methods=['POST'])
def login():
    data = request.json

    username = data['username']
    password = data['password']

    conn = connect_to_db()
    cur = conn.cursor()

    cur.execute("select * from users where pseudo=%s",(username,))

     # Fetch the first result
    user = cur.fetchone()   
    if user and check_password_hash(user[3], password):
        access_token = create_access_token(identity=username)
        cur.execute("Select pokedollars from users where pseudo=%s",(username,))
        usermoney = cur.fetchone()   
        # socketio.emit('value_updated', {'money':float(usermoney[0]) ,'user':username},room=connected_users[username]) 
        return jsonify({'access_token': access_token,'money':float(usermoney[0])}), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 401
    
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
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
          cur.execute(sql, (username,email,generate_password_hash(password),2500    ))
          conn.commit()
          return jsonify({'message': 'User registered successfully'}), 201
      except Exception as e:
          conn.rollback()
          return jsonify({"error": str(e)})
      finally:
          cur.close()
          conn.close()
      

@app.route('/changePassword', methods=['POST'])
@jwt_required()
def changePAssword():
    newPassword = request.json['password']
    current_user = get_jwt_identity() 
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("update users set  password=%s where pseudo=%s",(generate_password_hash(newPassword),current_user,))
    conn.commit()    
    cur.execute("Select pokedollars from users where pseudo=%s",(current_user,))
    cur.close()
    conn.close()
    return jsonify({'message':'succes change password'}), 200

@app.route('/deleteAccount', methods=['PUT'])
@jwt_required()
def deleteAccount():
    current_user = get_jwt_identity()
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("delete from users where pseudo=%s",(current_user,))
    conn.commit()  
    cur.execute("delete from collection where userid=%s",(current_user,))
    conn.commit()    
    cur.close()
    conn.close()
    return jsonify({'message':'succes change delete account'}), 200
   
    

@app.route('/addCardToUserCollection', methods=['PUT'])
@jwt_required()
def addCardToUserCollection():
    cards=request.get_json()
    current_user = get_jwt_identity()
    conn = connect_to_db()
    cur = conn.cursor()
    result=[]
    dict_counts = Counter(json.dumps(item, sort_keys=True) for item in cards)
    distinct_cards_with_counts = [{'object': json.loads(item), 'count': count} for item, count in dict_counts.items()]
    sql = "INSERT INTO collection (userid,setid,cardid,quantity) VALUES (%s, %s, %s, %s) ON CONFLICT (userid,cardid) DO UPDATE SET quantity=(collection.quantity+EXCLUDED.quantity)"
    try:
        cur.executemany(sql, ((current_user,card['object']['set']['id'],card['object']['id'],card['count']) for card in distinct_cards_with_counts))
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


@app.route('/getDataSets', methods=['GET'])
def getDataSets():
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT json_build_object('id',id,'data',data,'total_cards',total_cards,'avg_price_cards',avg_price_cards) from sets ")
    results = cur.fetchall()    
    cur.close()
    conn.close()
    return jsonify([row[0] for row in results]), 200


@app.route('/getDataCards/<string:set_id>', methods=['GET'])
def getDataCards(set_id):
    conn = connect_to_db()
    cur = conn.cursor()
    sql="SELECT data from cards where set_id=%s"
    cur.execute(sql,(set_id,))
    results = cur.fetchall()  
    cur.close()
    conn.close()
    return jsonify([row[0] for row in results]), 200




@app.route('/buyBoosters', methods=['POST'])
@jwt_required()
def buyBoosters():
    current_user = get_jwt_identity()
    data=request.get_json()
    amount=data['money']
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("Select pokedollars from users where pseudo='"+current_user+"'")
    usermoney = float(cur.fetchone()[0]) 
    if(amount<usermoney):
        cur.execute("UPDATE users SET pokedollars= %s where pseudo=%s ",(usermoney-amount,current_user,))
        conn.commit()
        # Emit message to the user's socket
        socketio.emit('value_updated', {'money': usermoney - amount, 'user': current_user}, room=connected_users[current_user])

        return jsonify({'money':'true'}), 200
    else:
        return  jsonify({'money':'false'}), 200



@app.route('/getUserData', methods=['GET'])
@jwt_required()
def getUserData():
    current_user = get_jwt_identity()
    conn = connect_to_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users where pseudo=%s", (current_user,))
    results = cur.fetchone()    
    cur.close()
    conn.close()
    socketio.emit('value_updated', {'money': float(results[5]), 'user': current_user}, room=connected_users[current_user])
    return jsonify({'money':float(results[5]),'user':results[1],'email':results[2]}), 200


@app.route('/scrapSetsAndCards', methods=['GET'])
def scrapp():
    conn = connect_to_db()
    cur = conn.cursor()
    headers = {'X-Api-Key': '6ef86c9f-633b-4411-a6cd-1d8b01533a46',}
    datasets = requests.get('https://api.pokemontcg.io/v2/sets', headers=headers).json()['data']
    sql = "INSERT INTO sets (id,total_cards,data) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET total_cards=sets.total_cards,data=sets.data"
    filter=['dv1','basep', 'si1', 'np', 'dpp', 'ru1', 'hsp', 'bwp', 'mcd11', 'mcd12', 'xyp', 'xy0', 'mcd16', 'smp', 'mcd19', 'swshp', 'mcd14', 'mcd15', 'mcd18', 'mcd17', 'mcd21', 'bp', 'fut20', 'tk1a', 'tk1b', 'tk2a', 'tk2b', 'mcd22', 'svp', 'sve']
    

    cur.executemany(sql,((dataset['id'],dataset['total'],json.dumps(dataset))  for dataset in datasets if dataset['id'] not in filter))
    conn.commit()
    for set in datasets:
        print(set['id'])
        if(set['id'] not in filter):
            cards=requests.get('https://api.pokemontcg.io/v2/cards?q=set.id:'+set['id'], headers=headers).json()['data']
            sql = "INSERT INTO cards (id,data,set_id) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET data=cards.data,set_id=cards.set_id"
            cur.executemany(sql,((card['id'],json.dumps(card),card['set']['id']) for card in cards))
            conn.commit()
    cur.close()
    conn.close()
    return jsonify({'money':'success'}), 200


@app.route('/param', methods=['GET'])
def param():
    conn = connect_to_db()
    cur = conn.cursor()
    headers = {'X-Api-Key': '6ef86c9f-633b-4411-a6cd-1d8b01533a46',}
    datasets = requests.get('https://api.pokemontcg.io/v2/sets', headers=headers).json()['data']
    sql = "INSERT INTO sets (id,total_cards,data) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET total_cards=sets.total_cards,data=sets.data"
    filter=['dv1','basep', 'si1', 'np', 'dpp', 'ru1', 'hsp', 'bwp', 'mcd11', 'mcd12', 'xyp', 'xy0', 'mcd16', 'smp', 'mcd19', 'swshp', 'mcd14', 'mcd15', 'mcd18', 'mcd17', 'mcd21', 'bp', 'fut20', 'tk1a', 'tk1b', 'tk2a', 'tk2b', 'mcd22', 'svp', 'sve']
    #tcg=['sv4', 'sv3Pt5', 'sv3', 'sv2', 'sv1', 'swsh12Pt5', 'swsh12', 'swsh11', 'swshTCGxGO', 'swsh10', 'swsh9', 'swsh8', 'swsh25', 'swsh7', 'swsh6', 'swsh5', 'swsh4Pt5', 'swsh4', 'swsh3Pt5', 'swsh3', 'swsh2', 'swsh1', 'sm12', 'sm11Pt5', 'sm11', 'sm10', 'smGum', 'sm9', 'sm8', 'sm7Pt5', 'sm7', 'sm6', 'sm5', 'sm4', 'sm3Pt5', 'sm3', 'sm2', 'sm1', 'xy12', 'xy11', 'xy10', 'xy9Pt5', 'xy9', 'xy8', 'xy7', 'xy6', 'xy5Pt5', 'xy5', 'xy4', 'xy3', 'xy2', 'xy1', 'bw11', 'bw10', 'bw9', 'bw8', 'bw7', 'bw6Pt5', 'bw6', 'bw5', 'bw4', 'bw3', 'bw2', 'bw1']
    for set in datasets:
        print(set['id'])
        if(set['id']not in filter):
            sql = "select distinct (data->'rarity') from cards where set_id=%s"
            res=cur.execute(sql,(set['id'],))





