import time
import random
import sys, subprocess
import math
import json
from colorama import just_fix_windows_console
from termcolor import colored
#from blessings import Terminal
#from rich import print


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
inv = []
pathWeight = [] #create pathWeight
for a in list(level.keys()):  pathWeight.append(level[a]["weight"]) #add weights from level.json to pathWeight





def move():
    valid = False   #generic while loop ender
    pathChoices = random.randint(2, 5)  #how many places can the player go to?
    pathView = random.choices(list(level.keys()), weights = pathWeight, k = pathChoices)    #choose the actual paths for the amount of path choices
    
    while valid != True:   #loop, player decides where to go in overworld
        for a in range(pathChoices):    #display path choices with descriptions
            print(f"{a+1}.) {pathView[a]}: {level[pathView[a]]["description"]}\n")
        playerChoice = int(input(f"Select path (1-{pathChoices}) -->"))  #input
        match playerChoice: #check how many path choices there are and allow valid number inputs for pathChoices
            case 1: valid = True
            case 2: valid = True
            case 3 if pathChoices >= 3: valid = True
            case 4 if pathChoices >= 4: valid = True
            case 5 if pathChoices >= 5: valid = True
        subprocess.run('clear', shell=True)
    
    match level[pathView[playerChoice - 1]]["type"]:
        case "dung": dung(pathView[playerChoice - 1])
        case "buff": buff(pathView[playerChoice - 1])
        case "shop": shop(pathView[playerChoice - 1])
        case "boss": boss(pathView[playerChoice - 1])

        
        




def dung(alevel):
    print(alevel)
    
    
    
    
def buff(alevel):
    valid = False
    match alevel:
        case "Smithery":
            print("a")
        case "Church":
            print("b")


def shop(alevel):
    print(alevel)
    
    
    
def boss(alevel):
    print(alevel)


def fight(enemy):
    print("fa")








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
                inv.append(item["Copper Sword"])
            case "B":
                difficulty = "intermediate"
                Stats.update([("maxHP", 500), ("HP", 500), ("strengthMult", 1.25)])
                inv.append(item["Copper Sword"])
            case "C":
                difficulty = "hard"
                Stats.update([("maxHP", 250), ("HP", 250), ("strengthMult", 1)])
                inv.append(item["Copper Sword"])
            case "D":
                difficulty = "impossible"
                Stats.update([("maxHP", 100), ("HP", 100), ("strengthMult", 0.5)])
                inv.append(item["Copper Dagger"])
        subprocess.run('clear', shell=True)
    print(data["Intro Text 1"][difficulty]) #Import text from data json
    print(Stats)
    print(inv)
    move()











run()