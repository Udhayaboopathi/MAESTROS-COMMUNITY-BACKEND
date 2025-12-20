"""Music/JioSaavn API Router"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import requests
import json
import re
import jiosaavn_endpoints as endpoints
import jiosaavn_helper as helper

router = APIRouter()


def search_for_song(query: str, lyrics: bool = False, songdata: bool = True):
    """Search for a song by query or URL"""
    if query.startswith('http') and 'saavn.com' in query:
        song_id = get_song_id(query)
        return get_song(song_id, lyrics)

    search_url = endpoints.search_base_url + query
    response = requests.get(search_url).text.encode().decode('unicode-escape')
    pattern = r'\(From "([^"]+)"\)'
    response = json.loads(re.sub(pattern, r"(From '\1')", response))
    song_response = response['songs']['data']
    
    if not songdata:
        return song_response
    
    songs = []
    for song in song_response:
        song_id = song['id']
        song_data = get_song(song_id, lyrics)
        if song_data:
            songs.append(song_data)
    return songs


def get_song(song_id: str, lyrics: bool = False):
    """Get song details by ID"""
    try:
        song_url = endpoints.song_details_base_url + song_id
        song_response = requests.get(song_url).text.encode().decode('unicode-escape')
        song_response = json.loads(song_response)
        song_data = helper.format_song(song_response[song_id], lyrics)
        if song_data:
            return song_data
    except Exception:
        return None


def get_song_id(url: str):
    """Extract song ID from JioSaavn URL"""
    res = requests.get(url, data=[('bitrate', '320')])
    try:
        return res.text.split('"pid":"')[1].split('","')[0]
    except IndexError:
        return res.text.split('"song":{"type":"')[1].split('","image":')[0].split('"id":"')[-1]


def get_album(album_id: str, lyrics: bool = False):
    """Get album details by ID"""
    try:
        response = requests.get(endpoints.album_details_base_url + album_id)
        if response.status_code == 200:
            songs_json = response.text.encode().decode('unicode-escape')
            songs_json = json.loads(songs_json)
            return helper.format_album(songs_json, lyrics)
    except Exception as e:
        print(f"Error fetching album: {e}")
        return None


def get_album_id(input_url: str):
    """Extract album ID from JioSaavn URL"""
    res = requests.get(input_url)
    try:
        return res.text.split('"album_id":"')[1].split('"')[0]
    except IndexError:
        return res.text.split('"page_id","')[1].split('","')[0]


def get_playlist(list_id: str, lyrics: bool = False):
    """Get playlist details by ID"""
    try:
        response = requests.get(endpoints.playlist_details_base_url + list_id)
        if response.status_code == 200:
            songs_json = response.text.encode().decode('unicode-escape')
            songs_json = json.loads(songs_json)
            return helper.format_playlist(songs_json, lyrics)
        return None
    except Exception as e:
        print(f"Error fetching playlist: {e}")
        return None


def get_playlist_id(input_url: str):
    """Extract playlist ID from JioSaavn URL"""
    res = requests.get(input_url).text
    try:
        return res.text.split('"type":"playlist","id":"')[1].split('"')[0]
    except IndexError:
        return res.text.split('"page_id","')[1].split('","')[0]


def search_playlist(query: str):
    """Search for playlist by name and return first result ID"""
    search_url = endpoints.search_base_url + query
    response = requests.get(search_url).text.encode().decode('unicode-escape')
    pattern = r'\(From "([^"]+)"\)'
    response = json.loads(re.sub(pattern, r"(From '\1')", response))
    
    if 'playlists' in response and 'data' in response['playlists']:
        playlists = response['playlists']['data']
        if playlists and len(playlists) > 0:
            return playlists[0].get('id')
    return None


def search_album(query: str):
    """Search for album by name and return first result ID"""
    search_url = endpoints.search_base_url + query
    response = requests.get(search_url).text.encode().decode('unicode-escape')
    pattern = r'\(From "([^"]+)"\)'
    response = json.loads(re.sub(pattern, r"(From '\1')", response))
    
    if 'albums' in response and 'data' in response['albums']:
        albums = response['albums']['data']
        if albums and len(albums) > 0:
            return albums[0].get('id')
    return None


def get_lyrics_by_id(song_id: str):
    """Get lyrics by song ID"""
    url = endpoints.lyrics_base_url + song_id
    lyrics_json = requests.get(url).text
    lyrics_text = json.loads(lyrics_json)
    return lyrics_text['lyrics']


# FastAPI Endpoints

@router.get("/")
async def music_home():
    """Music API information endpoint"""
    return {
        "status": True,
        "message": "Maestros Community JioSaavn Music API",
        "endpoints": {
            "/music/song/?query=": "Search for a song",
            "/music/song/get/?id=": "Get song details by ID",
            "/music/playlist/?query=": "Search for a playlist",
            "/music/album/?query=": "Search for an album",
            "/music/lyrics/?query=": "Get lyrics by song link or ID",
            "/music/result/?query=": "Get result by song/album/playlist link or search term"
        }
    }


@router.get("/song/")
async def search_song(
    query: str = Query(..., description="Song name or JioSaavn URL"),
    lyrics: bool = Query(False, description="Include lyrics in response"),
    songdata: bool = Query(True, description="Include full song data")
):
    """Search for a song"""
    songs = search_for_song(query, lyrics, songdata)
    
    # Extract required fields from first song
    if isinstance(songs, list) and len(songs) > 0:
        first_song = songs[0]
        if first_song:
            duration_seconds = int(first_song.get('duration', 0))
            duration_minutes = round(duration_seconds / 60, 2)
            
            return {
                "song": first_song.get('song', ''),
                "album": first_song.get('album', ''),
                "image": first_song.get('image', ''),
                "media_url": first_song.get('media_url', ''),
                "duration": duration_minutes,
                "music": first_song.get('music', ''),
                "singers": first_song.get('singers', ''),
                "year": first_song.get('year', '')
            }
    elif isinstance(songs, dict):
        duration_seconds = int(songs.get('duration', 0))
        duration_minutes = round(duration_seconds / 60, 2)
        
        return {
            "song": songs.get('song', ''),
            "album": songs.get('album', ''),
            "image": songs.get('image', ''),
            "media_url": songs.get('media_url', ''),
            "duration": duration_minutes,
            "music": songs.get('music', ''),
            "singers": songs.get('singers', ''),
            "year": songs.get('year', '')
        }
    
    raise HTTPException(status_code=404, detail="Song not found")


@router.get("/song/get/")
async def get_song_details(
    id: str = Query(..., description="JioSaavn song ID"),
    lyrics: bool = Query(False, description="Include lyrics in response")
):
    """Get song details by ID"""
    resp = get_song(id, lyrics)
    if not resp:
        raise HTTPException(status_code=404, detail="Invalid Song ID received!")
    return resp


@router.get("/playlist/")
async def search_playlist_endpoint(
    query: str = Query(..., description="Playlist name or JioSaavn URL"),
    lyrics: bool = Query(False, description="Include lyrics in response")
):
    """Search for a playlist"""
    # Check if query is a URL or search term
    if 'http' in query and 'saavn' in query:
        playlist_id = get_playlist_id(query)
    else:
        # Search for playlist by name
        playlist_id = search_playlist(query)
        if not playlist_id:
            raise HTTPException(status_code=404, detail="No playlist found for the given query!")
    
    songs = get_playlist(playlist_id, lyrics)
    if not songs:
        raise HTTPException(status_code=500, detail="Failed to fetch playlist data!")
    
    # Extract all song details with 8 fields
    formatted_songs = []
    if 'songs' in songs and isinstance(songs['songs'], list):
        for song in songs['songs']:
            if song:
                duration_seconds = int(song.get('duration', 0))
                duration_minutes = round(duration_seconds / 60, 2)
                
                formatted_song = {
                    "song": song.get('song', ''),
                    "album": song.get('album', ''),
                    "image": song.get('image', ''),
                    "media_url": song.get('media_url', ''),
                    "duration": duration_minutes,
                    "music": song.get('music', ''),
                    "singers": song.get('singers', ''),
                    "year": song.get('year', '')
                }
                formatted_songs.append(formatted_song)
    
    return {"songs": formatted_songs, "count": len(formatted_songs)}


@router.get("/album/")
async def search_album_endpoint(
    query: str = Query(..., description="Album name or JioSaavn URL"),
    lyrics: bool = Query(False, description="Include lyrics in response")
):
    """Search for an album"""
    # Check if query is a URL or search term
    if 'http' in query and 'saavn' in query:
        album_id = get_album_id(query)
    else:
        # Search for album by name
        album_id = search_album(query)
        if not album_id:
            raise HTTPException(status_code=404, detail="No album found for the given query!")
    
    songs = get_album(album_id, lyrics)
    if not songs:
        raise HTTPException(status_code=500, detail="Failed to fetch album data!")
    
    # Extract all song details with 8 fields
    formatted_songs = []
    if 'songs' in songs and isinstance(songs['songs'], list):
        for song in songs['songs']:
            if song:
                duration_seconds = int(song.get('duration', 0))
                duration_minutes = round(duration_seconds / 60, 2)
                
                formatted_song = {
                    "song": song.get('song', ''),
                    "album": song.get('album', ''),
                    "image": song.get('image', ''),
                    "media_url": song.get('media_url', ''),
                    "duration": duration_minutes,
                    "music": song.get('music', ''),
                    "singers": song.get('singers', ''),
                    "year": song.get('year', '')
                }
                formatted_songs.append(formatted_song)
    
    return {"songs": formatted_songs, "count": len(formatted_songs)}


@router.get("/lyrics/")
async def get_lyrics(
    query: str = Query(..., description="Song link or ID")
):
    """Get lyrics by song link or ID"""
    try:
        if 'http' in query and 'saavn' in query:
            song_id = get_song_id(query)
            lyrics_text = get_lyrics_by_id(song_id)
        else:
            lyrics_text = get_lyrics_by_id(query)
        
        return {
            "status": True,
            "lyrics": lyrics_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/")
async def get_result(
    query: str = Query(..., description="Song/Album/Playlist URL or search term"),
    lyrics: bool = Query(False, description="Include lyrics in response")
):
    """Get result by song/album/playlist link or search term"""
    if 'saavn' not in query:
        return search_for_song(query, lyrics, True)
    
    try:
        if '/song/' in query:
            song_id = get_song_id(query)
            song = get_song(song_id, lyrics)
            return song

        elif '/album/' in query:
            album_id = get_album_id(query)
            songs = get_album(album_id, lyrics)
            return songs

        elif '/playlist/' in query or '/featured/' in query:
            playlist_id = get_playlist_id(query)
            songs = get_playlist(playlist_id, lyrics)
            return songs
        
        raise HTTPException(status_code=400, detail="Invalid URL format")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
