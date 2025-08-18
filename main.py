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
difficulty = None   #difficulty, first asked variable
Stats = {}
pathWeight = [] #create pathWeight
for a in list(level.keys()):  pathWeight.append(level[a]["weight"]) #add weights from level.json to pathWeight



def move():
    valid = False   #generic while loop ender
    pathChoices = random.randint(2, 5)  #how many places can the player go to?
    pathView = random.choices(list(level.keys()), weights = pathWeight, k = pathChoices)    #choose the actual paths for the amount of path choices
    
    while valid == False:   #loop, player decides where to go in overworld
        for a in range(pathChoices):    #display path choices with descriptions
            print(f"{a+1}.) {pathView[a]}: {level[pathView[a]]["description"]}\n")
        PlayerChoice = input(f"Select path (1-{pathChoices}) -->")  #input
        match PlayerChoice: #check how many path choices there are and allow valid number inputs for pathChoices
            case "1":
                print("chose path 1")
                valid = True
            case "2":
                print("chose path 2")
                valid = True
            case "3" if pathChoices >= 3:
                print("chose path 3")
                valid = True
            case "4" if pathChoices >= 4:
                print("chose path 4")
                valid = True
            case "5" if pathChoices >= 5:
                print("chose path 5")
                valid = True
        subprocess.run('clear', shell=True)






def run():
    
    
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