from flask import Flask
from flask import request
import requests
import copy
import json
import time
import mysql.connector
from mysql.connector import Error
import re
import os
import sys
import shlex
import subprocess

app = Flask(__name__)

with open(os.path.join(os.pardir, "api_keys/api_keys.json")) as f:
    data = json.load(f)
    slack_token = data["slack_token"]
    weather_token = data["weather_token"]
    slack_incoming = data["slack_incoming_token"]

latex_template_path = "template.tex"
latex_template_replace_text = "$ equation goes here $"
output_path = "/var/www/html/latex"
OUTPUT_PATH = "/var/www/html/latex"
message_url = 'https://slack.com/api/chat.postMessage'
reaction_url = 'https://slack.com/api/reactions.add'
file_url = 'https://slack.com/api/files.upload'
delete_url = 'https://slack.com/api/chat.delete'
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
def delete_message(data):
    header['Content-Type'] = 'application/json'
    send_message = {
            'token': slack_token,
            'channel': data["event"]["channel"],
            'ts': data["event"]["ts"]
    }
    r = requests.post(delete_url,data=json.dumps(send_message), headers=header)
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

def latex_doc(equation):
    """Load the LaTeX template from the global macro path, add the input
    equation to its appropriate place in the middle, and return the text to be
    compiled as a string.
    """
    with open(latex_template_path, "r") as f:
        template = f.read()

    return template.replace(latex_template_replace_text, equation)

header = {
	'Authorization': 'Bearer '+slack_token
}
def send_image(data, image_path):
    payload = {
        "token": slack_token,
        "channels": [data["event"]["channel"]]
    }
    pic = open(image_path, 'rb')
    my_file = {
        'file': ('anime.jpg', pic, 'png')
    }
    channel = data["event"]["channel"]
    send_image_cmd = f'curl -F file=@{image_path} -F channels={channel} -H "Authorization: Bearer {slack_token}" https://slack.com/api/files.upload' 
    subprocess.run(shlex.split(send_image_cmd), check=True)
    #r = requests.post(file_url,params =payload, file = my_file, headers=header)
    pic.close()
    #print(r.content)
    return

def write_file(path, text):
    with open(path, "w") as f:
        f.write(text)

def send_latex(data, text):
    doc = latex_doc(text)
    t = time.time() # save the time for consistency across later operations
    path = "template1.tex"
    write_file(path, doc)

    # Compile the document to PDF using pdfLaTeX
    latex_cmd = "pdflatex template1.tex"
    subprocess.run(shlex.split(latex_cmd), check=True)

    # Convert the PDF to PNG
    convert_cmd = ("pdftoppm template1.pdf latex_image -png -rx 800 "
            "-ry 800")
    subprocess.run(shlex.split(convert_cmd), check=True)

    # Send the converted image to GroupMe
    send_image(data, image_path="latex_image-1.png")
    delete_message(data)


current_process = set()
#called on messages which we want to handle
def handle_event(data):
    current_process.add(json.dumps(data))
    try:
        text = data["event"]["text"]
        b = True
    except:
        b=False
    if b:
        add_groceries_match = re.search(re_dict["add_groceries_re"], data["event"]["text"].lower())
        rem_groceries_match = re.search(re_dict["rem_groceries_re"], data["event"]["text"].lower())
        if data["event"]["text"].startswith("$") and data["event"]["text"].endswith("$"):
            send_latex(data, text)
        elif data["event"]["text"].startswith("[;") and data["event"]["text"].endswith(";]"):
            text = text.strip("[]; ")
            send_latex(data, text)
        elif data["event"]["text"].replace(" ", "").lower() == "clippyweather":
            send_weather(data)
        elif data["event"]["text"].replace(" ", "").lower() == "clippygroceries":
            all_groceries(data)
        elif add_groceries_match:
            add_groceries(data, add_groceries_match)
        elif rem_groceries_match:
            rem_groceries(data, rem_groceries_match)
    current_process.remove(json.dumps(data))



###############################################################################


@app.route('/event', methods=['POST'])
def incoming():
	incoming_data = request.json
	if incoming_data["event_time"] > start_time and \
        json.dumps(incoming_data) not in current_process and \
        incoming_data["token"] == slack_incoming and \
	incoming_data["event"].get("subtype") != "bot_message":
		handle_event(incoming_data)

	return "done"

if __name__ == '__main__':
	start_time = time.time()
	app.run(debug= False, host='0.0.0.0')
