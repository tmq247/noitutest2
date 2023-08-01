import json
import logging
import os

logger = logging.getLogger(__name__)

# Load constants from config file
filename = "config_beta.json" if os.getenv("BETA") else "config.json"
logger.info("Loading constants from config file")
with open(filename) as f:
    config = json.load(f)

TOKEN = config["6272942112:AAF9Y6U0B2ZyQ2hdsQ9D_ETT8VtlhzXiDO4"]    #5036197906:AAEs-DDN0X_DCa8K66zYQsXkz5w8GSaFgtI
ON9BOT_TOKEN = config["6226805699:AAE1T96RKSjs06kNID7VW9xVsYaSOFDI92o"]   #5093671528:AAEpbDvCfJdb2ZFK1i9rSHupGqoZTHC1sI4
DB_URI = config["mongodb+srv://minhquang24071996:2407@coihaycoc.1an4oky.mongodb.net/?retryWrites=true&w=majority"]   #mongodb+srv://agarta01:44malatya22@cluster0.advkm.mongodb.net/myFirstDatabase?retryWrites=true&w=majority
PROVIDER_TOKEN = config["PROVIDER_TOKEN"]
OWNER_ID = config["5838967403"]  #5038665445
ADMIN_GROUP_ID = config["-1001854415088"]   #-1001793811732
OFFICIAL_GROUP_ID = config["-1001854415088"]  #-1001793811732
WORD_ADDITION_CHANNEL_ID = config["-1001854415088"]   #-1001602923043
VIP = config["coihaycoc"]   #Dnztrmn
VIP_GROUP = config["coihaycoc247"]   #Keyfialemsohbet

WORDLIST_SOURCE = "https://raw.githubusercontent.com/tmq247/noitutest/main/src/assets/tudien.txt"    #https://raw.githubusercontent.com/dwyl/english-words/master/words.txt

STAR = "\u2b50\ufe0f"


class GameState:
    JOINING = 0
    RUNNING = 1
    KILLGAME = -1


class GameSettings:
    JOINING_PHASE_SECONDS = 60
    MAX_JOINING_PHASE_SECONDS = 180
    MIN_PLAYERS = 2
    MAX_PLAYERS = 50
    INCREASED_MAX_PLAYERS = 300
    MIN_TURN_SECONDS = 30
    MAX_TURN_SECONDS = 50
    TURN_SECONDS_REDUCTION_PER_LIMIT_CHANGE = 5
    MIN_WORD_LENGTH_LIMIT = 3
    MAX_WORD_LENGTH_LIMIT = 10
    WORD_LENGTH_LIMIT_INCREASE_PER_LIMIT_CHANGE = 1
    TURNS_BETWEEN_LIMITS_CHANGE = 5

    ELIM_JOINING_PHASE_SECONDS = 90
    ELIM_MIN_PLAYERS = 5
    ELIM_MAX_PLAYERS = 30
    ELIM_INCREASED_MAX_PLAYERS = 50
    ELIM_TURN_SECONDS = 30
    ELIM_MAX_TURN_SCORE = 20
