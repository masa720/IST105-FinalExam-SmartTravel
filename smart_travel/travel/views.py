from django.shortcuts import render
import requests
from datetime import datetime
import json
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .form import TravelForm

# MongoDB connection
def get_mongodb_client():
    """Connect to MongoDB database"""
    try:
        client = MongoClient('localhost', 27017)
        return client
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        return None

def save_travel_query(start_city, end_city, route_summary):
    """Save user travel query to MongoDB database"""
    try:
        client = get_mongodb_client()
        if client:
            db = client.smart_travel_db
            collection = db.travel_queries

            query_data = {
                'start_city': start_city,
                'end_city': end_city,
                'timestamp': datetime.now(),
                'route_summary': route_summary
            }

            result = collection.insert_one(query_data)
            return result.inserted_id
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")
        return None

def get_travel_history():
    """Get all travel queries from MongoDB database"""
    try:
        client = get_mongodb_client()
        if client:
            db = client.smart_travel_db
            collection = db.travel_queries

            queries = list(collection.find().sort('timestamp', -1))
            return queries
    except Exception as e:
        print(f"Error getting history from MongoDB: {e}")
        return []

def get_bc_cities():
    """Get list of cities in BC from GeoDB API"""
    url = "http://geodb-free-service.wirefreethought.com/v1/geo/countries/CA/regions/BC/cities?limit=10"
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Smart-Travel-Planner/1.0'
    }

    response = requests.get(url, headers=headers, timeout=10)
    data = response.json()

    cities = []  # Empty list to store city data
    for city_data in data.get('data', []):  # Loop through each city
        cities.append({
            'name': city_data.get('name', ''),
            'latitude': city_data.get('latitude', 0),
            'longitude': city_data.get('longitude', 0)
        })

    return cities

def get_coordinates(city):
    """Find latitude and longitude for a city name"""
    cities = get_bc_cities()
    for city_data in cities:
        if city_data['name'].lower() == city.lower():
            return city_data['latitude'], city_data['longitude']
    return None, None

def index(request):
    """Main page - show form and travel results"""
    weather_start = None
    weather_end = None
    route_details = None
    travel_advice = None

    if request.method == "POST":
        form = TravelForm(request.POST)
        if form.is_valid():
            start_city = form.cleaned_data['start_city']
            end_city = form.cleaned_data['end_city']

            weather_start = get_weather(start_city)
            weather_end = get_weather(end_city)

            route_details = get_route(start_city, end_city)

            # Get travel advice using Pacific Time (BC timezone)
            from datetime import timezone, timedelta
            pacific_tz = timezone(timedelta(hours=-8))  # BC time is UTC-8
            current_time = datetime.now(pacific_tz)
            travel_advice = get_travel_advice(weather_start, weather_end, current_time)

            # Save to MongoDB
            route_summary = json.dumps({
                'distance': route_details['distance'] if route_details else 0,
                'duration': route_details['duration'] if route_details else 0,
                'steps_count': len(route_details['steps']) if route_details else 0
            })

            save_travel_query(start_city, end_city, route_summary)

    else:
        form = TravelForm()

    return render(request, 'travel/index.html', {
        'form': form,
        'weather_start': weather_start,
        'weather_end': weather_end,
        'route_details': route_details,
        'travel_advice': travel_advice,
        'cities': get_bc_cities()  # Pass cities to template
    })

def history(request):
    """History page - show past travel queries"""
    travel_queries = get_travel_history()
    return render(request, 'travel/history.html', {
        'travel_queries': travel_queries
    })

def get_weather(city):
    """Get weather information for a city using OpenWeatherMap API"""
    api_key = os.getenv('OPENWEATHERMAP_API_KEY')
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}"
    response = requests.get(url)
    data = response.json()
    try:
        temp_kelvin = data['main']['temp']
        temp_celsius = temp_kelvin - 273.15  # Change Kelvin to Celsius
        description = data['weather'][0]['description']
        return {
            'temperature': round(temp_celsius, 1),
            'description': description
        }
    except Exception as e:
        print(f"Weather parsing error: {e}")
        return {
            'temperature': '',
            'description': ''
        }

def get_route(start, end):
    """Get driving route between two cities using OpenRouteService API"""
    start_lat, start_lon = get_coordinates(start)
    end_lat, end_lon = get_coordinates(end)

    api_key = os.getenv('OPENROUTESERVICE_API_KEY')
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        "Authorization": api_key,
        "Accept": "application/json"
    }
    # OpenRouteService needs coordinates as [longitude, latitude]
    body = {
        "coordinates": [
            [start_lon, start_lat],
            [end_lon, end_lat]
        ]
    }
    try:
        response = requests.post(url, json=body, headers=headers)
        data = response.json()
        if 'routes' not in data or not data['routes']:
            print(f"Route API error: {data}")
            return {
                'distance': 0,
                'duration': 0,
                'steps': []
            }
        route = data['routes'][0]
        segment = route['segments'][0]
        steps = segment.get('steps', [])
        distance = round(segment.get('distance', 0) / 1000, 1)  # Change meters to km
        duration = round(segment.get('duration', 0) / 60, 1)    # Change seconds to minutes
        step_list = []
        for step in steps:
            step_list.append({
                'instruction': step.get('instruction', ''),
                'distance': round(step.get('distance', 0) / 1000, 2)
            })
        return {
            'distance': distance,
            'duration': duration,
            'steps': step_list
        }
    except Exception as e:
        print(f"Route parsing error: {e}")
        return {
            'distance': 0,
            'duration': 0,
            'steps': []
        }

def get_travel_advice(weather_start, weather_end, current_time):
    """Give travel advice based on weather and time"""
    current_hour = current_time.hour
    bad_weather_conditions = ['rain', 'snow', 'storm', 'thunderstorm']

    # Check if weather data exists
    start_desc = weather_start['description'] if weather_start and 'description' in weather_start else ''
    end_desc = weather_end['description'] if weather_end and 'description' in weather_end else ''

    # Look for bad weather in both cities
    start_weather_bad = any(condition in start_desc.lower() for condition in bad_weather_conditions)
    end_weather_bad = any(condition in end_desc.lower() for condition in bad_weather_conditions)

    # Use if/elif/else to decide travel advice
    if start_weather_bad or end_weather_bad:
        return "Consider delaying your trip due to bad weather."
    elif current_hour >= 23 or current_hour <= 4:
        return "Consider delaying your trip due to bad weather."
    else:
        return "Good time to start your trip!"
