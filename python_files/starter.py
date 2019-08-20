from flask import Flask
from flask import request
import requests
import json
import time
import mysql.connector
from mysql.connector import Error
import re
import os

app = Flask(__name__)

with open(os.path.join(os.pardir, "api_keys/api_keys.json")) as f:
	data = json.load(f)
	slack_token = data["slack_token"]
	weather_token = data["weather_token"]


message_url = 'https://slack.com/api/chat.postMessage'
reaction_url = 'https://slack.com/api/reactions.add'
weather_url = 'http://api.openweathermap.org/data/2.5/weather?id=5206379&APPID={}&units=imperial'.format(weather_token)
start_time = 0
re_dict = {}
re_dict["add_groceries_re"] = "clippy.*add(.*)to.*(groceries)|(grocery list)"
re_dict["rem_groceries_re"] = "clippy.*(?:(?:remove)|(?:delete))(.*)from.*(groceries)|(grocery list)"

header = {
	'Content-Type': 'application/json',
	'Authorization': 'Bearer '+slack_token
}

#Function to send query to database and return response
def db_query(query, params):
	resp = ""
	try:
		connection = mysql.connector.connect(host='localhost',
											 database='slack',
											 user='root',
											 password='Vatsal@2409')
		if connection.is_connected():
			db_Info = connection.get_server_info()
			print("Connected to MySQL Server version ", db_Info)
			cursor = connection.cursor()
			cursor.execute(query, params)
			try:
				resp = cursor.fetchall()
			except:
				print("nothing to fetch")
			connection.commit()
	except Error as e:
		print("Error while connecting to MySQL", e)
	finally:
		if (connection.is_connected()):
			cursor.close()
			connection.close()
			print("MySQL connection is closed")
	return resp
############################ Handling Events ##################################
#get list of all users from group
def all_users():
	users=requests.get('https://slack.com/api/users.list?token='+slack_token)
	users = json.loads(users.content)["members"]
	return {d["id"]:d["real_name"] for d in users if True}

users = all_users()

#simple function which responds echos the message
def echo(data):
	send_message = {
		'token': slack_token,
		'channel': data["event"]["channel"],
		'text': data["event"]["text"]
	}
	r = requests.post(message_url,data=json.dumps(send_message), headers=header)
#sends weather data from pittsburgh to same channel
def send_weather(data):
	weather = json.loads(requests.get(weather_url).content)
	str_weather="The weather outside is {}. It's {} degrees out with a humidity\
	 of {} percent".format(weather["weather"][0]["main"], \
	 weather["main"]["temp"], weather["main"]["humidity"])
	send_message = {
		'token': slack_token,
		'channel': data["event"]["channel"],
		'text': str_weather.replace("\t", "")
	}
	r = requests.post(message_url,data=json.dumps(send_message), headers=header)


def all_groceries(data):
	groceries = db_query("SELECT * FROM groceries;", ())
	groceries_string = "Here's what people want: \n"
	for item in groceries:
		groceries_string += "{} for {}\n".format(item[0], item[1])
	send_message = {
		'token': slack_token,
		'channel': data["event"]["channel"],
		'text': groceries_string
	}
	r = requests.post(message_url,data=json.dumps(send_message), headers=header)

def add_groceries(data, match):
	q = "INSERT INTO groceries (item, user) VALUES (%s, %s)"
	vals = (match.group(1).strip(), users[data["event"]["user"]])
	db_query(q, vals)
	send_message = {
		'token': slack_token,
		'channel': data["event"]["channel"],
		'text': "Ok I put it in"
	}
	r = requests.post(message_url,data=json.dumps(send_message), headers=header)

def rem_groceries(data, match):
	pot_item = match.group(1).strip().lower()
	q_c = "SELECT item FROM groceries WHERE item=%s"
	q_d = "DELETE FROM groceries WHERE item=%s"
	vals = (pot_item,)
	print(pot_item)
	items = db_query(q_c, vals)
	if len(items) == 0:
		response = "Couldn't find that. Could you try again?"
	elif len(items) == 1:
		db_query(q_d, vals)
		response = "Ok did it"
	else:
		response = "Too many matches"
	send_message = {
		'token': slack_token,
		'channel': data["event"]["channel"],
		'text': response
	}
	r = requests.post(message_url,data=json.dumps(send_message), headers=header)



#called on messages which we want to handle
def handle_event(data):
	# if data["event"]["channel"] == 'CLWMU4HT6': #bot test channel
	# 	echo(data)
		add_groceries_match = re.search(re_dict["add_groceries_re"], data["event"]["text"].lower())
		rem_groceries_match = re.search(re_dict["rem_groceries_re"], data["event"]["text"].lower())
		if data["event"]["text"].replace(" ", "").lower() == "clippyweather":
			send_weather(data)
		elif data["event"]["text"].replace(" ", "").lower() == "clippygroceries":
			all_groceries(data)
		elif add_groceries_match:
			add_groceries(data, add_groceries_match)
		elif rem_groceries_match:
			rem_groceries(data, rem_groceries_match)



###############################################################################


@app.route('/event', methods=['POST'])
def incoming():
	incoming_data = request.json
	if incoming_data["event_time"] > start_time and \
	incoming_data["event"].get("subtype") != "bot_message":
		handle_event(incoming_data)

	return "done"

if __name__ == '__main__':
	start_time = time.time()
	app.run(debug= False, host='0.0.0.0')