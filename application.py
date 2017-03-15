from flask import Flask, request, jsonify, g
import os, sqlite3


#Gets the directory the database is contained in
curDir = os.path.dirname(os.path.realpath('__file__'))
dbDir = os.path.join(curDir, "db")
DATABASE = str(dbDir) + "\EloDB.db"
#

application = Flask(__name__)


#Searches for the username and password, and returns the corresponding userid if found, and -1 if not
def validate_user(username, password):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    data = cur.fetchone()
    cur.close()

    if data is not None:
        return int(data['userid'])

    return -1


#Connects to and returns the database
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)

    db.row_factory = make_dicts

    return db

#Makes dicts out of the sqlite rows
def make_dicts(cursor, row):
    return dict((cursor.description[idx][0], value)
                for idx, value in enumerate(row))


@application.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


#"hello world"
@application.route('/')
def index():
    cur = get_db().cursor()
    cur.close()
    return "Hello, world! Working so far."


#Creates tables for users, players, games, elo, and hist
@application.route('/init')
def initDB():
    cur = get_db().cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT, userid INT);")
    cur.execute("CREATE TABLE IF NOT EXISTS players (playername TEXT, playerid INT, userid INT);")
    cur.execute("CREATE TABLE IF NOT EXISTS games (gamename TEXT, userid INT, gameid INT, numplayers INT, teamsize INT, halfpointsallowed BOOLEAN);")
    cur.execute("CREATE TABLE IF NOT EXISTS elo (elonum INT, userid INT, playerid INT, gameid INT);")
    cur.execute("CREATE TABLE IF NOT EXISTS hist (histtext TEXT, userid INT, playerid INT, gameid INT, timestamp TEXT);")

    cur.close()

    return "Done!"

'''

    POST methods:

'''
# POSTing to /login with a username and password verifies that the person trying to access this system is a valid user
# JSON structure: {"username": user_name, "password": password}
@application.route('/login', methods=['POST'])
def log_in():
    username = request.json['username']
    password = request.json['password']
    try:
        if validate_user(username, password) is not -1:
            return "Authenticated. Welcome, %s!" %(username)

    except Exception as err:
        print(str(err))

    return "Username or password is incorrect."


# POSTing to '/signup' creates a new user with a username, password, and userid in the DB if it does not already exist
# JSON structure: {"username": user_name, "password": password}
@application.route('/signup', methods=['POST'])
def make_user():
    cur = get_db().cursor()
    user_name = request.json['username']
    password = request.json['password']
    cur.execute("SELECT * FROM users WHERE username = ?", (user_name,))
    data = cur.fetchall()

    if len(data) > 0:
        cur.close()
        return "That username already exists!"

    #Create a unique userid for the user based on already existing ids
    cur.execute("SELECT * FROM users")
    data = cur.fetchall()
    max = 0
    for entry in data:
        if max < int(entry['userid']):
            max = int(entry['userid'])

    max += 1 #New user id

    cur.execute("INSERT INTO users (username, password, userid) VALUES (?, ?, ?)", (user_name, password, max,))
    get_db().commit()
    cur.close()

    return "User created!"

# POSTing to '/mkplayer' creates a new player and updates the player with a default Elo for each existing gametype
# JSON structure: {"username": user_name, "password": password, "plname": player_name}
@application.route('/mkplayer', methods=['POST'])
def make_player():
    cur = get_db().cursor()
    user_name = request.json['username']
    password = request.json['password']
    player_name = request.json['plname']

    #First, check credentials
    userid = validate_user(user_name, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"
    #

    #Then, select all players matching this user's id, check if the player name is unique, and create a unique playerid
    cur.execute("SELECT * FROM players WHERE userid = ?", (userid,))
    data = cur.fetchall()
    max = 0
    for entry in data:
        if entry['playername'] == player_name:
            cur.close()
            return "Player already exists!"
        if max < int(entry['playerid']):
            max = int(entry['playerid'])

    playerid = max + 1
    #

    #Inserts the new player into players, and for each gametype with this user's id, inserts a new default elo (1400) in elo along with
    #the corresponding user, player, and game ids
    cur.execute("INSERT INTO players (playername, playerid, userid) VALUES (?,?,?)", (player_name, playerid, userid))
    cur.execute("SELECT * FROM games WHERE userid = ?", (userid,))
    data = cur.fetchall()
    for entry in data:
        gameid = entry['gameid']
        cur.execute("INSERT INTO elo (elonum, userid, playerid, gameid) VALUES (?,?,?,?)", (1400, userid, playerid, gameid))

    get_db().commit()
    #

    return "Player created!"


# POSTing to '/mkgame' creates a new gametype and updates each existing player with a default Elo for that gametype
# JSON structure: {"username": user_name, "password": password, "gname":  game_name, "nplayers": num_players, "teamsize": team_size, "halfpoints": 'y'/'n'}
@application.route('/mkgame', methods=['POST'])
def make_game():
    cur = get_db().cursor()
    user_name = request.json['username']
    password = request.json['password']
    game_name = request.json['gname']
    num_players = request.json['nplayers']
    teamsize = request.json['teamsize']
    hp = request.json['halfpoints']
    halfpoints = False
    if hp == 'y':
        halfpoints = True

    #Validate the user
    userid = validate_user(user_name, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"
    #

    #Check to make sure the game name is unique for this user, and get a new, unique game id for the game to be added
    cur.execute("SELECT * FROM games WHERE userid = ?", (userid,))
    data = cur.fetchall()
    max = 0
    for entry in data:
        if entry['gamename'] == game_name:
            cur.close()
            return "Gametype already exists!"
        if max < int(entry['gameid']):
            max = int(entry['gameid'])

    gameid = max + 1
    #

    #Insert the new game in games, and update each of the user's players' elos
    cur.execute("INSERT INTO games (gamename, userid, gameid, numplayers, teamsize, halfpointsallowed) VALUES (?, ?, ?, ?, ?, ?)",
                (game_name, userid, gameid, num_players, teamsize, halfpoints))
    cur.execute("SELECT * FROM players WHERE userid = ?", (userid,))
    data = cur.fetchall()
    for entry in data:
        playerid = entry['playerid']
        cur.execute("INSERT INTO elo (elonum, userid, playerid, gameid) VALUES (?,?,?,?)", (1400, userid, playerid, gameid))

    get_db().commit()
    cur.close()
    #

    return "Game created!"


# POSTing to '/record' records the game that was just calculated. The corresponding players have their Elo and Hist fields updated
"""
    JSON structure:
        {
            "username":user_name, "password": password
            "teams" : [ ['team_1_mem_1', 'team_1_mem_2'], ['team_2_mem_1', 'team_2_mem_2'] ],
            "teamscores" : ['team_1_score', 'team_2_score'],
            "team elo gains" : [ ['team_1_mem_1_gain', 'team_1_mem_2_gain'], ['team_2_mem_1_gain', 'team_2_mem_2_gain'] ],
            "gname": game_name,
            "timestamp" : timestamp
        }
"""
@application.route('/record', methods=['POST'])
def record_game():
    cur = get_db().cursor()
    username = request.json['username']
    password = request.json['password']
    game_name = request.json['gname']

    #Validate user
    userid = validate_user(username, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"
    #

    #Verify that the gametype exists
    cur.execute("SELECT * FROM games WHERE userid = ? AND gamename = ?", (userid, game_name,))
    data = cur.fetchone()
    gameid = 0
    if data is not None:
        gameid = data['gameid']
    else:
        cur.close()
        return "Gametype not found"
    #

    team_list = request.json['teams']
    team_score_list = request.json['teamscores']
    team_elo_gains = request.json['team elo gains']
    timestamp = request.json['timestamp']

    #For each team in the list
    for i in range(len(team_list)):
        #For each player in that team
        for j in range(team_list[i]):
            #Check if the player exists for this user
            player = team_list[i][j]
            cur.execute("SELECT * FROM players WHERE userid = ? AND playername = ?", (userid, player,))
            data = cur.fetchone()
            playerid = 0
            if data is not None: #The player exists
                playerid = data['playerid']

                #Create the history string
                hist_str = ""

                #Pop the current team from the team_list to get the opponents
                opponents = list(team_list)
                opponents.pop(i)
                if int(team_score_list[i]) == 1:
                    hist_str = str(team_list[i]) + " beat " + str(opponents) + " at " + str(game_name)
                elif int(team_score_list[i]) == 0:
                    hist_str = str(team_list[i]) + " lost to " + str(opponents) + " at " + str(game_name)
                else:
                    hist_str = str(team_list[i]) + " tied " + str(opponents) + " at " + str(game_name)

                #Insert into hist table
                cur.execute("INSERT INTO hist (histtext, userid, playerid, gameid, timestamp) VALUES (?,?,?,?,?)",
                            (hist_str, userid, playerid, gameid, timestamp))

                #Update player elo
                cur.execute("SELECT * FROM elo WHERE userid = ? AND playerid = ? AND gameid = ?", (userid, playerid, gameid,))
                data = cur.fetchone()
                if data is not None:
                    elo = data['elonum']
                    elo += int(team_elo_gains[i][j])
                else:
                    cur.close()
                    return "A very odd error occured. That's not good at all."

                cur.execute("UPDATE elo SET elonum = ? WHERE userid = ? AND playerid = ? AND gameid = ?", (elo, userid, playerid, gameid,))
                #

    get_db().commit()
    cur.close()
    return "Updated player histories and elos"


'''

    PUT methods:

'''
# PUTing to '/setelo/<player_name>' updates player_name with a new Elo for the specified gametype
# JSON structure: {"username": user_name, "password": password, "pname" : player_name, "gname" : game_name, "elo" : new_elo}
@application.route('/setelo', methods=['PUT'])
def set_elo():
    cur = get_db().cursor()
    user_name = request.json['username']
    password = request.json['password']
    player_name = request.json['pname']
    game_name = request.json['gname']
    new_elo = request.json['elo']

    #Validate the user
    userid = validate_user(user_name, password)
    if userid == -1:
        cur.close()
        return "Invalid credentials"
    #

    #Check to see if the gametype exists for this user, and get the gameid
    cur.execute("SELECT * FROM games WHERE userid = ? AND gamename = ?", (userid, game_name,))
    data = cur.fetchone()
    gameid = 0
    if data is not None:
        gameid = int(data['gameid'])
    else:
        cur.close()
        return "Gametype not found"
    #

    #Check to see if the player exists for this user and get the userid
    cur.execute("SELECT * FROM players WHERE userid = ? AND playername = ?", (userid, player_name,))
    data = cur.fetchone()
    playerid = 0
    if data is not None:
        playerid = data['playerid']
    else:
        cur.close()
        return "Player not found"
    #

    cur.execute("UPDATE elo SET elonum = ? WHERE userid = ? AND gameid = ? AND playerid = ?", (int(new_elo), userid, gameid, playerid,))
    get_db().commit()
    cur.close()

    return "Updated!"

''''''


'''

    DELETE methods:

'''
# DELETEing to '/player' deletes a player from the players table
# JSON structure: {"username": user_name, "password": password, "pname" : player_name}
@application.route('/player', methods=['DELETE'])
def delete_player():
    cur = get_db().cursor()
    username = request.json['username']
    password = request.json['password']
    player_name = request.json['pname']

    #Validate user
    userid = validate_user(username, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"
    #

    #Check to make sure the player exists, then remove them from the players table, and their entries from the elo table
    cur.execute("SELECT * FROM players WHERE userid = ? AND playername = ?", (userid, player_name, ))
    data = cur.fetchone()
    playerid = 0
    if data is not None:
        playerid = int(data['playerid'])
    else:
        cur.close()
        return "Player not found"

    cur.execute("DELETE FROM players WHERE playerid = ? AND userid = ?", (playerid, userid,))
    cur.execute("SELECT * FROM elo WHERE playerid = ? AND userid = ?", (playerid, userid, ))
    data = cur.fetchall()
    for entry in data:
        gameid = int(entry['gameid'])
        cur.execute("DELETE FROM elo WHERE playerid = ? AND userid = ? AND gameid = ?", (playerid, userid, gameid, ))

    get_db().commit()
    cur.close()
    #

    return "Player deleted"


# DELETEing to '/game' deletes a game from the games table, as well as any entries in the elo table corresponding to that user and game
# JSON structure: {"username": user_name, "password": password, "gname": game_name}
@application.route('/game', methods=['DELETE'])
def delete_game():
    cur = get_db().cursor()
    username = request.json['username']
    password = request.json['password']
    game_name = request.json['gname']

    #Validate user
    userid = validate_user(username, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"
    #

    #Check that this gametype exists
    cur.execute("SELECT * FROM games WHERE userid = ? AND gamename = ?", (userid, game_name,))
    data = cur.fetchone()
    gameid = 0
    if data is not None:
        gameid = data['gameid']
    else:
        cur.close()
        return "Gametype not found"
    #

    #Delete it from the table, and any corresponding entries from the elo table
    cur.execute("DELETE FROM games WHERE userid = ? AND gamename = ?", (userid, game_name,))
    cur.execute("DELETE FROM elo WHERE userid = ? AND gameid = ?", (userid, gameid,))
    get_db().commit()
    cur.close()
    #

    return "Gametype deleted"
''''''


'''

    GET methods:

'''
# GETing '/players' returns a jsonified version of the players for this user
@application.route('/players/<username>/<password>', methods=['GET'])
def get_players(username, password):
    cur = get_db().cursor()

    #Validate the user
    userid = validate_user(username, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"

    #Get all of the players matching this user's id
    cur.execute("SELECT * FROM players WHERE userid = ?", (userid,))
    data = cur.fetchall()

    #Make a dictionary out of the returned players
    ret_dict = {}
    for entry in data:
        ret_dict[entry['playername']] = {"playerid":entry['playerid'], "userid":entry['userid']}

    #Return the jsonified version of this dictionary
    return jsonify(ret_dict)

# GETing '/games' returns a jsonified version of the games table for this user
@application.route('/games/<username>/<password>', methods=['GET'])
def get_gametypes(username, password):
    cur = get_db().cursor()

    #Validate the user
    userid = validate_user(username, password)
    if userid == -1:
        cur.close()
        return "Invalid Credentials"

    #Get all of the games matching this user's id
    cur.execute("SELECT * FROM games WHERE userid = ?", (userid, ))
    data = cur.fetchall()

    #Make a dict out of the data returned
    ret_dict = {}
    for entry in data:
        ret_dict[entry['gamename']] = {"userid":entry['userid'], "gameid":entry['gameid'], "numplayers":entry['numplayers'],
                                       "teamsize":entry['teamsize'], "halfpointsallowed":entry['halfpointsallowed']}

    return jsonify(ret_dict)
''''''


if __name__ == "__main__":
    application.debug = True
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=True)
