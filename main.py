import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv
import pandas as pd
import tkinter as tk
import threading
from PIL import ImageTk as itk
from PIL import Image
import webbrowser
import urllib
import tensorflow as tf
import numpy as np
from sklearn import preprocessing
from sklearn.model_selection import train_test_split

#load client id and client secret (specified in .env file)... for future reference: https://stackoverflow.com/questions/40216311/reading-in-environment-variables-from-an-environment-file
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USERNAME = os.getenv('USERNAME')
redirect_uri = "http://localhost:8888/callback"
scope = 'user-read-currently-playing'

seedPlaylist = "6ozBeqb7QP6g8C7sRynf8w?si=2heeBEyPRkOdzAPC5nqpEA" #define initial playlist to look at

nnModelPath = "nn_model" #define path for neural network model save file
nnModelGlobal = None #define empty variable to put neural network model into

 #authenticate things for analysis... here: https://medium.com/@maxtingle/getting-started-with-spotifys-api-spotipy-197c3dc6353b (actually confused --> this is different everywhere I look)
client_credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

#authenticate for currently playing
def setup_spotipy_user_object():
    token = util.prompt_for_user_token(USERNAME, scope, CLIENT_ID, CLIENT_SECRET, redirect_uri)
    return spotipy.Spotify(auth=token)

spUser = setup_spotipy_user_object()

def scale_user_rating_data(userRatings): #scale model inputs to be between 0 and 1
    returnList = []
    for rating in userRatings:
        returnList.append((rating+10)/20) #scale -10 to 10 to 0 to 1 
    return returnList

def save_user_data(): #saves user scoring data
    global initialSongsDF

    print("saving user data...")
    initialSongsDF.to_csv("UserPlaylistData.csv", index=False) #save user data as csv
    print(initialSongsDF)

def analyze_playlist(creator, playlist_id): #function originally from: https://github.com/MaxHilsdorf/introduction_to_spotipy/blob/master/introduction_to_spotipy.ipynb
    
    # Create empty dataframe
    playlist_features_list = ["artist", "album", "track_name", "track_id", 
                             "danceability", "energy", "key", "loudness", "mode", "speechiness",
                             "instrumentalness", "liveness", "valence", "tempo", "duration_ms", "time_signature",
                             "UserRating"] #UserRating is score given by user 
    playlist_df = pd.DataFrame(columns = playlist_features_list)
    
    # Create empty dict
    playlist_features = {}
    
    # Loop through every track in the playlist, extract features and append the features to the playlist df
    # print(sp.user_playlist_tracks(creator, playlist_id))
    playlist = sp.user_playlist_tracks(creator, playlist_id)["tracks"]["items"]
    for track in playlist:
        # Get metadata
        playlist_features["artist"] = track["track"]["album"]["artists"][0]["name"]
        playlist_features["album"] = track["track"]["album"]["name"]
        playlist_features["track_name"] = track["track"]["name"]
        playlist_features["track_id"] = track["track"]["id"]
        # Get audio features
        audio_features = sp.audio_features(playlist_features["track_id"])[0] #information on these here: https://developer.spotify.com/documentation/web-api/reference/#object-audiofeaturesobject
        for feature in playlist_features_list[4:16]:
            playlist_features[feature] = audio_features[feature]
        
        # Concat the dfs
        track_df = pd.DataFrame(playlist_features, index = [0])
        playlist_df = pd.concat([playlist_df, track_df], ignore_index = True)
        
    return playlist_df

def get_song_info(spObject):
    trackInfo = spObject.current_user_playing_track() #get track info for current track

    artist = trackInfo["item"]["artists"][0]["name"] #get first artist listed 
    songName = trackInfo["item"]["name"] #get song name
    albumName = trackInfo["item"]["album"]["name"] #get album name
    albumImageUrl = trackInfo['item']['album']['images'][0]['url'] #get album image url
    songId = trackInfo['item']['id']

    #download album image
    resource = urllib.request.urlopen(albumImageUrl)
    output = open("albumCover.jpg", 'wb')
    output.write(resource.read())
    output.close()

    #get album loaded into python essentially 
    albumImage = itk.PhotoImage(Image.open("albumCover.jpg"))

    #reset user rank choice
    if (trackInfo["item"]["duration_ms"] - trackInfo["progress_ms"]) <= 1001:
         userRatingVar.set(0) #reset user rating

    return ((artist, songName, albumName, albumImage, songId))

def set_tk_widgets(): #set all song/album/artist/albumImage vars in tkinter display
    global spUser

    threading.Timer(1, set_tk_widgets).start() #run with threading

    #make sure still authenticated 
    try: 
        songInfo = get_song_info(spUser)
    except:
        spUser = setup_spotipy_user_object()
        songInfo = get_song_info(spUser)

    #set text widget variables
    artistText.set("By: " + songInfo[0])
    albumText.set("Album: " + songInfo[2])
    songText.set("Song: " + songInfo[1])

    #set album image
    albumImageTK.configure(image=songInfo[3])
    albumImageTK.image = songInfo[3]

    #get user rating if already rated 
    if not initialSongsDF[initialSongsDF["track_id"].str.contains(songInfo[4])].empty: #check if song already listed in dataframe. Citation for part of this: https://stackoverflow.com/questions/21319929/how-to-determine-whether-a-pandas-column-contains-a-particular-value (though this answer was actually wrong?)
        currentUserRatingVar.set("Your Current Rating: " + str(initialSongsDF.loc[initialSongsDF.track_id == songInfo[4], "UserRating"].values[0]))
        set_model_predicted_rating() #set variable for current model prediction if user has already rated song

    else: #if no entry exists, set as "nan"
        currentUserRatingVar.set("Your Current Rating: nan")

        modelPredictionText.set("Model's Prediction: hidden") #don't display model prediction if user hasn't rated yet

def save_score():
    global initialSongsDF 

    #define all song attributes (from analyze_playlist function)
    playlist_features_list = ["artist", "album", "track_name", "track_id", 
                             "danceability", "energy", "key", "loudness", "mode", "speechiness",
                             "instrumentalness", "liveness", "valence", "tempo", "duration_ms", "time_signature", 
                             "UserRating"] #UserRating is score given by user 

    trackInfo = spUser.current_user_playing_track() #get info on current track

    song_features = {} #create empty dict

    #extract song data
    song_features["artist"] = trackInfo["item"]["artists"][0]["name"]
    song_features["album"] = trackInfo["item"]["album"]["name"]
    song_features["track_name"] = trackInfo["item"]["name"]
    song_features["track_id"] = trackInfo["item"]["id"]
    # Get audio features
    audio_features = sp.audio_features(song_features["track_id"])[0] #information on these here: https://developer.spotify.com/documentation/web-api/reference/#object-audiofeaturesobject
    for feature in playlist_features_list[4:16]:
        song_features[feature] = audio_features[feature]

    #check if song already recorded 
    if not initialSongsDF[initialSongsDF["track_id"].str.contains(song_features["track_id"])].empty: #check if song already listed in dataframe. Citation for part of this: https://stackoverflow.com/questions/21319929/how-to-determine-whether-a-pandas-column-contains-a-particular-value (though this answer was actually wrong?)
        initialSongsDF.loc[initialSongsDF.track_id == song_features["track_id"], "UserRating"] = userRatingVar.get() #set value for UserRating for the song with the same track id (same song)
    else:
        print("adding song data to dataframe due to it not being present yet...")
        song_features["UserRating"] = userRatingVar.get() #set user rating inside dict before concatination
        #add song to dataframe if it doesn't exsist
        track_df = pd.DataFrame(song_features, index=[0])
        initialSongsDF = pd.concat([initialSongsDF, track_df], ignore_index=True)

    print("Saved score for the song {} as {}".format(song_features["track_name"], userRatingVar.get()))
    save_user_data() #save this to file

def _get_training_inputs():
    global initialSongsDF

    tempInitialSongDF = initialSongsDF.copy() #make copy to not risk damage to original 
    tempInitialSongDF.dropna(inplace=True) #remove all None values

    DFOnlyInputs = tempInitialSongDF.iloc[:, 4:16] #get dataframe without input values... citation: https://stackoverflow.com/questions/11285613/selecting-multiple-columns-in-a-pandas-dataframe
    inputValues = np.asarray(DFOnlyInputs.values) #get input values (data spotify has on each song or song attributes)

    return inputValues

def create_nn_model(): #create tensorflow neural network 

    inputs = tf.keras.layers.Input(shape=(12,)) #define input shape
    dense1 = tf.keras.layers.Dense(12, activation="tanh")(inputs)
    dense2 = tf.keras.layers.Dense(24)(dense1)
    dense3 = tf.keras.layers.Dense(48)(dense2)
    output = tf.keras.layers.Dense(1, activation="linear")(dense3)
    model = tf.keras.models.Model(inputs=inputs, outputs=output)

    model.compile(optimizer="Adam", loss="mse", metrics=["mae", "acc"])

    return model

def load_saved_nn_model(): #load model saved as file
    global nnModelGlobal 
    global nnModelPath

    try: 
        model = create_nn_model()

        model.load_weights(nnModelPath)

        nnModelGlobal = model
    except: 
        print("No saved nn model, leaving undefined")

def set_model_predicted_rating():
    global nnModelGlobal
    global initialSongsDF

    artist, songName, albumName, albumImage, songId = get_song_info(spUser)

    prefix = "Model's Prediction: " #set prefix for variable

    if not initialSongsDF[initialSongsDF["track_id"].str.contains(songId)].empty: #check if listed in dataframe
        #if listed, can display 

        onlySpecificSongDF = initialSongsDF[initialSongsDF["track_id"] == songId]
        songDataAsList = onlySpecificSongDF.values.tolist()[0][4:16] #convert dataframe to list, take first row as will be only row, constrain to values that are interesting.

        songInformation = np.asarray([songDataAsList]) #extract song data from dataframe into numpy array 

        #scale input data same way it was trained
        scaler = preprocessing.MinMaxScaler()
        scaler.fit(_get_training_inputs())
        songInformation = scaler.transform(songInformation)

        if nnModelGlobal != None: #if the model has been trained 
            modelPredictionValue = nnModelGlobal.predict(songInformation)

            modelPredictionValue = (modelPredictionValue - 0.5) * 20 #rescale prediction to how the user rates songs

        else:
            print("no model defined")
            modelPredictionValue = "none"

        modelPredictionText.set(prefix + str(modelPredictionValue))
    else:
        print("can't set, not listed in dataframe yet. Try saving a score first.")
        modelPredictionText.set(prefix + "hidden") #don't display if not saved yet/don't have data

def train_a_model():
    global initialSongsDF
    global nnModelPath
    global nnModelGlobal

    epochs = 5000

    inputValues = _get_training_inputs()

    #set up scaler 
    scaler = preprocessing.MinMaxScaler()
    scaler.fit(inputValues)

    inputValues = scaler.transform(inputValues) #scale data to allow model to get better fit

    tempInitialSongDF = initialSongsDF.copy() #make copy to not risk damage to original 
    tempInitialSongDF.dropna(inplace=True) #remove all None values

    outputValues = np.asarray(scale_user_rating_data(tempInitialSongDF["UserRating"].values)) #get all user ratings for above songs

    X_train, X_test, y_train, y_test = train_test_split(inputValues, outputValues, test_size=0.33) #split input output into training and testing sets

    if len(outputValues) < 40: #don't train if there isn't that much data
        print("Not enough data to train off of")
    else:
        print(inputValues[0])
        print(outputValues)
        
        #create model (neural network)
        model = create_nn_model()

        model.fit(x=X_train, y=y_train, epochs=epochs)
        
        model.evaluate(X_test, y_test)

        model.save_weights(nnModelPath)

        nnModelGlobal = model


#set up window
window = tk.Tk()
window.title("Spotify Recommendation Engine")
window.geometry("652x800")

#setup tkinter vars 
artistText = tk.StringVar()
albumText = tk.StringVar()
songText = tk.StringVar()
modelPredictionText = tk.StringVar()

songInfo = get_song_info(spUser)
albumImage = songInfo[3]

userRatingVar = tk.IntVar()
userRatingVar.set(0)

currentUserRatingVar = tk.StringVar()

#setup tkinter widgets 
albumImageTK = tk.Label(window, image=albumImage)
albumImageTK.place(x=5,y=5)

artistLabel = tk.Label(window, padx=15, pady=15, textvariable=artistText)
artistLabel.place(x=50, y=662)
albumLabel = tk.Label(window, padx=15, pady=15, textvariable=albumText)
albumLabel.place(x=50, y=702)
songLabel = tk.Label(window, padx=15, pady=15, textvariable=songText)
songLabel.place(x=50, y=742)

currentUserRatingLabel = tk.Label(window, padx=15, pady=15, textvariable=currentUserRatingVar)
currentUserRatingLabel.place(x=285, y=662)

userRating = tk.Spinbox(window, from_=-10, to=10, textvariable=userRatingVar)
userRating.place(x=300, y=702)

confirmRatingButton = tk.Button(window, text="Confirm Rating", padx=5, pady=5, relief="raised", justify="center", height=1, command=save_score)
confirmRatingButton.place(x=300, y=742)

trainModelButton = tk.Button(window, text="Re-Train Model", padx=5, pady=5, relief="raised", justify="center", height=1, command=train_a_model)
trainModelButton.place(x=500, y=742)

modelPredictionValueLabel = tk.Label(window, padx=10, pady=10, textvariable=modelPredictionText)
modelPredictionValueLabel.place(x=500, y=702)


#try to load old user data, upon failing, create new data based on seeded playlist
try:
    initialSongsDF = pd.read_csv("UserPlaylistData.csv")
except:
    print("Failed to find old user data, creating new data off of seeded playlist")
    initialSongsDF = analyze_playlist(USERNAME, seedPlaylist)

print(initialSongsDF)
set_tk_widgets()
window.mainloop()