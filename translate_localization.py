#!/usr/bin/env python3

#
# Marius Montebaur
# 
# Oktober 2023
# 


import sys
import json
from typing import Dict, List
from chat_gpt_interface import ChatGPT
from tokens import CHATGPT_TOKEN


task_description = """
I want you to translate some text from German to English.
This text will be used to offer an iOS app in different languages.
The input given to you will consist of three lines for each phrase that needs to be translated.
First, the phrase in German.
Second, a comment that describes in which context the phrase is occuring in the application's UI. Make sure that the translation you provide fits this context.
Thrid, a line starting with "translation: " in which you should add your translation.

Please return only the lines starting with "translation:" with your added translation after the colon. Do not include the comments in the translations, those are only to add context.
"""

additional_context_info = """
In the data you will be given, the word "Zähler" refers to a digital power meter or an electricity meter. Do not translate it with "counter".
"""


class Translatable:

    def __init__(self, key, info_dict):
        self.key = key
        self.info_dict = info_dict
    
    def is_translated_in(self, language: str = "en"):
        if "localizations" in self.info_dict:
            l10ns = self.info_dict["localizations"]
            return language in l10ns.keys()
        return False
    
    def get_gpt_query(self) -> str:
        query = f"key: {self.key}\n"
        comment = self.info_dict["comment"] if "comment" in self.info_dict else "No comment provided."
        query += f"comment: {comment}\n"
        query += "translation: \n"
        return query

    def parse_gpt_response(self, gpt_response: str, overwrite=False, for_language="en") -> bool:
        """ Returns True if parsing was successful. """
        try:
            translation = gpt_response
            if not translation.startswith("translation: "):
                return False
            
            translation = translation[len("translation: "):]

            localizations_dict_update = {
                for_language: {
                    "stringUnit": {
                        "state": "translated",
                        "value": translation
                    }
                }
            }

            if "localizations" in self.info_dict:
                self.info_dict["localizations"].update(localizations_dict_update)
            else:
                self.info_dict["localizations"] = localizations_dict_update
            
            return True
        except:
            pass

        return False


def main():

    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <path to Localizable.xcstrings>")
        return

    # Path to the Xcode projects. Searches for swift files and will localize them in place
    localizable_file = sys.argv[1]

    print("Warning: This script add the translations in-place, i.e. modify the original provided file!")
    print("If you don't have a version control system, this is not recommended!\n")
    answer = input("Please type 'yes' to continue or any other key to abort. ")
    if answer != "yes":
        print("\nAborting.")
        return
    

    with open(localizable_file, "r") as f:
        loc = json.loads(f.read())
    
    strings = loc["strings"]
    strings_objects: Dict[str, Translatable] = {}

    for key in strings.keys():
        string_info = strings[key]
        string_obj = Translatable(key, string_info)

        strings_objects[key] = string_obj

    
    ## build the query for chatGPT

    max_lines = None
    query = ""
    query_lines = []
    objects_in_this_query: List[Translatable] = []

    for i, key in enumerate(strings.keys()):
        str_obj = strings_objects[key]
        if str_obj.is_translated_in("en"):
            continue

        q = str_obj.get_gpt_query()
        query_lines.append(q)
        objects_in_this_query.append(str_obj)

        if max_lines and i >= max_lines:
            break


    ## send to chatGPT

    cpt = ChatGPT(CHATGPT_TOKEN, model="gpt-3.5-turbo")

    max_query_length = 30
    full_response = ""

    for i in range(0, len(query_lines)-1, max_query_length):

        query_idx = int(i/max_query_length + 1)
        print(f"running gpt query {query_idx}")

        query = query_lines[i: i+max_query_length]
        query_length = len(query)

        query = "\n".join(query)
        
        def is_response_valid_callback(response):
            lines = response.split("\n")
            non_empty_lines = [l for l in lines if l]

            valid = len(non_empty_lines) == query_length

            if not valid:
                print("query_length:", query_length)
                print("------- lines ---------", len(lines))
                print(lines)
                print("------- non empty lines ---------", len(non_empty_lines))
                print(non_empty_lines)

            return valid

        info = task_description + "\n" + additional_context_info

        response = cpt.complete_query(info, query, is_response_valid_callback)
        full_response += response + "\n"


    ## evaluate response

    valid_lines = 0
    valid_response = True

    for line in full_response.split("\n"):
        if not line:
            continue
        
        valid_response &= objects_in_this_query[valid_lines].parse_gpt_response(line, for_language="en")

        if not valid_response:
            print("invalid line")
            print(line)
            return

        valid_lines += 1

    
    ## write back to json

    for key in loc["strings"].keys():
        loc["strings"][key] = strings_objects[key].info_dict
    
    with open(localizable_file, "w") as f:
        f.write(json.dumps(loc, indent=2, separators=(', ', ' : '), ensure_ascii=False))



if __name__ == "__main__":
    main()

