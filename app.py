import os
import json
from flask import Flask, render_template, request, redirect, url_for, session
from WazeRouteCalculator import WazeRouteCalculator, WRCError
import math
import random
import requests
import random
import spotipy
from spotipy.oauth2 import SpotifyOAuth



app = Flask(__name__)
app.secret_key = "ofbhazofepijfpoaj"
app.config['SESSION_COOKIE_NAME'] = 'Spotify Cookie'

def generate_random_location(lat, lon, max_distance_km):
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    distance_km = random.uniform(0, max_distance_km)
    earth_radius = 6371.0  # Earth radius in kilometers

    bearing = random.uniform(0, 2 * math.pi)

    new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / earth_radius) +
                            math.cos(lat_rad) * math.sin(distance_km / earth_radius) * math.cos(bearing))
    new_lon_rad = lon_rad + math.atan2(math.sin(bearing) * math.sin(distance_km / earth_radius) * math.cos(lat_rad),
                                       math.cos(distance_km / earth_radius) - math.sin(lat_rad) * math.sin(new_lat_rad))

    new_lat = math.degrees(new_lat_rad)
    new_lon = math.degrees(new_lon_rad)

    return new_lat, new_lon

SPOTIPY_CLIENT_ID = os.getenv('f83f3706e93e4a2091d4749885bd4e0a')
SPOTIPY_CLIENT_SECRET = os.getenv('da2bb910a4654ce1b7857eb217db9a3e')
SPOTIPY_REDIRECT_URI = "http://localhost:5000/callback"

sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID, 
                        client_secret=SPOTIPY_CLIENT_SECRET, 
                        redirect_uri=SPOTIPY_REDIRECT_URI, 
                        scope="playlist-modify-public user-top-read")

def create_spotify_playlist(sp, travel_time):
    user_id = sp.current_user()['id']
    playlist_name = f"Road Trip Playlist - {travel_time} minutes"
    
    # Create the playlist in Spotify
    playlist = sp.user_playlist_create(user_id, playlist_name, public=True, description="Generated for your road trip")
    number_of_tracks = travel_time // 3
    top_tracks = sp.current_user_top_tracks(limit=50)
    song_uris = [track['uri'] for track in top_tracks['items']]
    songs_to_add = random.sample(song_uris, min(number_of_tracks, len(song_uris)))
    sp.playlist_add_items(playlist['id'], songs_to_add)

    # Return the playlist link
    return playlist['external_urls']['spotify']

@app.route('/callback', methods=['GET'])
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'], as_dict=True)
    session['token_info'] = token_info
    return redirect(url_for('index'))

# Function to get the country from latitude and longitude using OpenCage Geocoding API
def get_country_from_coordinates(latitude, longitude):
    api_key = "f6c481036a944d52b30ede1e3e4ee73f"  # Replace with your OpenCage API Key
    url = f"https://api.opencagedata.com/geocode/v1/json?q={latitude}+{longitude}&key={api_key}"

    response = requests.get(url)
    data = response.json()

    if data['results']:
        country = data['results'][0]['components']['country']
        return country
    else:
        return None

# Function to map the country to a Waze-supported region
def map_country_to_waze_region(country):
    country_to_region = {
        'United States': 'US',
        'Canada': 'US',
        'Mexico': 'US',
        'United Kingdom': 'EU',
        'France': 'EU',
        'Germany': 'EU',
        'Brazil': 'BR',
        'Israel': 'IL',
        'Morocco': 'EU',  # Map Morocco to the EU region
        # Add other mappings as necessary
    }
    return country_to_region.get(country, 'US')  # Default to 'US' if country is not found

# Route to render the main form
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET'])
def login():
    # Redirect to Spotify for authorization
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)
# Route to handle route generation
ORS_API_KEY = "5b3ce3597851110001cf6248bb883407386e4460a8c37ecde7d7b422"

def get_route_from_ors(origin_lat, origin_lon, destination_lat, destination_lon):
    url = f"https://api.openrouteservice.org/v2/directions/driving-car"
    origin_lat = float(request.form['latitude'])
    origin_lon = float(request.form['longitude'])
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "coordinates": [[origin_lon, origin_lat], [destination_lon, destination_lat]],
        "format": "geojson"
    }

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        route_data = response.json()
        return route_data['routes'][0]['geometry']['coordinates']  # The actual route coordinates
    else:
        return None

@app.route('/generate_route', methods=['POST'])
def generate_route():
    print("Generate route endpoint reached")
    if 'token_info' not in session:
        return redirect(url_for('login'))
    travel_time = int(request.form['time'])
    route_type = request.form['route_type']

    # Get user's current location (latitude, longitude)
    user_latitude = float(request.form['latitude'])
    user_longitude = float(request.form['longitude'])

    # Automatically detect the region based on the user's location
    country = get_country_from_coordinates(user_latitude, user_longitude)
    region = map_country_to_waze_region(country)

    # Default speed assumption: 60 km/h
    average_speed_kmh = 60

    # Placeholder for the destination
    destination = ""
    orig = (user_latitude, user_longitude)
    if route_type == 'random':
        # Calculate max distance based on travel time and speed
        max_distance_km = (travel_time / 60) * average_speed_kmh
        destination_lat, destination_lon = generate_random_location(user_latitude, user_longitude, max_distance_km)
        destination = f"{destination_lat}, {destination_lon}"
        dest = (destination_lat, destination_lon)
        route_coordinates = [orig, dest]
    else:
        # For round-trip, destination is the starting location
        destination = f"{user_latitude}, {user_longitude}"
        

    # Use WazeRouteCalculator to get the actual travel time and distance
    try:
        calc = WazeRouteCalculator(f"{user_latitude}, {user_longitude}", destination, region=region)
        actual_route_time, route_distance = calc.calc_route_info() 
        actual_route_time, route_distance = actual_route_time+(travel_time-actual_route_time), route_distance
        route_distance = (actual_route_time / 60) * average_speed_kmh
        if actual_route_time <= travel_time:
            # If the actual route time is less than expected, suggest extending the playlist
            route_info = (
                f"Route found: {route_distance} km, taking {actual_route_time} minutes. "
                f"You might want to extend your playlist as you’ll arrive faster than expected!"
            )

        else:
            route_info = f"Route found: {route_distance} km, taking {actual_route_time} minutes."
 
        token_info = session['token_info']
        sp = spotipy.Spotify(auth=token_info['access_token'])
        playlist_url = create_spotify_playlist(sp, travel_time)

        route_info = f"Route found: {route_distance} km, taking {actual_route_time} minutes. Here's your Spotify playlist: {playlist_url}"

    except WRCError as e:
        route_info = f"Error finding route: {e}"

    return render_template('map.html', coordinates=route_coordinates, route=route_info)

if __name__ == '__main__':
    app.run(debug=True)
