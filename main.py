import time
import random
import sys, subprocess
import math
import json
with open('data.json', 'r') as file:
    data = json.load(file)
with open('enemy.json', 'r') as file:
    enemy = json.load(file)
with open('item.json', 'r') as file:
    item = json.load(file)
with open('level.json', 'r') as file:
    level = json.load(file)
    
i = None
paths = []
difficulty = None
Stats = {}




def move():
    for a in list(level.keys()):
        paths.append(level[a]["weight"])
    print(paths)
    pathChoices = random.choices(list(level.keys()), weights = paths, k = random.randint(2, 5))
    for a in pathChoices:
        print(a)
        print(level[a]["description"])








def run():
    
    print(level["room"])
    
    i = input("|--Press Enter to Continue--|")
    subprocess.run('clear', shell=True)
    
    global difficulty
    while difficulty == None: #difficulty select
        i = input(data["Difficulty Prompt"])
        match i.upper():
            case "A":
                difficulty = "easy"
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 2)])
            case "B":
                difficulty = "intermediate"
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 1.25)])
            case "C":
                difficulty = "hard"
                Stats.update([("maxHP", 250), ("HP", 250), ("strengthMult", 1)])
            case "D":
                difficulty = "impossible"
                Stats.update([("maxHP", 100), ("HP", 100), ("strengthMult", 0.5)])
        subprocess.run('clear', shell=True)
    print(data["Intro Text 1"][difficulty]) #Import text from data json
    move()











run()