#===========================================================================================
# Capstone project - Quick Commute

# Written by
# Abhijith Rajan
# 07/12/2018

#===========================================================================================
from flask import Flask, render_template, request, redirect

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import os
import re
import requests
import pandas as pd
import json

import networkx as nx
import folium
#===========================================================================================

app = Flask(__name__, static_url_path = "", static_folder = "static")

#===========================================================================================
@app.route('/', methods=['GET','POST'])
def index():
    goog_api_key = os.environ.get('GOOG_API_KEY')

    if request.method == 'GET':
        def_map_lat, def_map_lng = 40.7128, -74.0060
#        map_options = GMapOptions(lat=def_map_lat, lng=def_map_lng, map_type="roadmap", zoom=11)
#        p = gmap(goog_api_key, map_options)
#        script, div = components(p)

        map_osm = folium.Map(location=[def_map_lat, def_map_lng])
        map_osm.choropleth(geo_data="BoroughBoundaries.geojson",
                   fill_opacity=0.5, line_opacity=0.2)#,fill_color='YlGn') 
        map_osm.save('templates/map_init.html')

        return render_template('index.html')

    elif request.method == 'POST':
        addr_pattern = "[\w\s\-\,\#\.\+]+"

        origin = request.form['origin']
        if not re.match(addr_pattern, origin):
            return render_template("error.html", errors="re-enter origin address")

        destination = request.form['dest']
        if not re.match(addr_pattern, destination):
            return render_template("error.html", errors="re-enter destination address")

        '''
        try:
            income = float(request.form['income'])
        except ValueError:
            return render_template("error.html", errors="re-enter income. Only numbers allowed.")
        '''

        lyft_token = lyft_init()

        gender = request.form['gender-select']
        education = request.form['education-select']


        goog_loc = google_init(origin, destination, goog_api_key)

        olat, olong = goog_loc['routes'][0]['legs'][0]['start_location']['lat'], goog_loc['routes'][0]['legs'][0]['start_location']['lng']
        geoid = get_tract_num(olat, olong)
        income = get_income(geoid, gender, education)

        graph, shortest = get_best_route(goog_loc, lyft_token, income)
        make_plot(shortest, graph)

        instr_text = ["Ride option for income = $" + str(int(income))]        
        for cnt in range(len(shortest)-1):
            instr_text.append( str(cnt) + ". " + graph.get_edge_data(shortest[cnt],shortest[cnt+1])[0]['instructions'] )

        return render_template('result.html', instr_text=instr_text) 

#===========================================================================================
@app.route('/get_map_init')
def get_map_init():
    return render_template('map_init.html')

#===========================================================================================
@app.route('/get_map_final')
def get_map_final():
    return render_template('map_final.html')

#===========================================================================================
def get_income(geoid, gender, education):

    inc_sex_edu = pd.read_csv("/Users/arajan/Downloads/ACS_16_5YR_B20004/ACS_16_5YR_B20004_with_ann_NYC.csv", header=0, index_col=0)
    for col in inc_sex_edu.columns:
        if not 'Geography' in col:
            inc_sex_edu[col] = pd.to_numeric(inc_sex_edu[col], errors='coerce') 
    inc_sex_edu.drop(['Geography','Total_Male','Total_Female'],axis=1, inplace=True)
    inc_sex_edu.dropna(how='all', thresh=5, inplace=True)

    inc_sex_edu.iloc[:,0:5] = inc_sex_edu.iloc[:,0:5].T.interpolate().T
    inc_sex_edu.iloc[:,0:5] = inc_sex_edu.iloc[:,0:5].iloc[:, ::-1].T.interpolate().T.iloc[:, ::-1]
    inc_sex_edu.iloc[:,5:] = inc_sex_edu.iloc[:,5:].T.interpolate().T
    inc_sex_edu.iloc[:,5:] = inc_sex_edu.iloc[:,5:].iloc[:, ::-1].T.interpolate().T.iloc[:, ::-1]

    income = inc_sex_edu.loc[inc_sex_edu.index==geoid, gender+'_'+education]
    
    if income.values:
        return income.values[0]
    else: 
        return 50000

#===========================================================================================
def get_best_route(locator, token, income_per_year):

    # Assuming working 40 hours a week, 
    # and there are 52 working weeks in the year.
    income_per_hour = income_per_year / 40 / 52 
    income_per_min = income_per_hour / 60

    # initiate multi-edge, directed Graph
    G = nx.MultiDiGraph()
    route = dict()

    fare_info = {'PATH':2.75, 'SUBWAY':2.75, 'BUS': 2.75}

    # Primary route with Lyft
    start_node = 0
    end_node = len(locator['routes'][0]['legs'][0]['steps'])

    start_location = locator['routes'][0]['legs'][0]['start_location']
    end_location = locator['routes'][0]['legs'][0]['end_location']

    start_lat, start_lng = start_location['lat'], start_location['lng']
    stop_lat, stop_lng = end_location['lat'], end_location['lng']

    lyft_r_eta = lyft_eta(start_lat, start_lng, token, rtype='lyft').json()
    eta_step_0 = lyft_r_eta['eta_estimates'][0]['eta_seconds']/60.

    lyft_r_step = lyft_request(start_lat, start_lng, stop_lat, stop_lng, token, rtype='lyft').json()
    dur_step = lyft_r_step['cost_estimates'][0]['estimated_duration_seconds']/60.

    price_step = lyft_r_step['cost_estimates'][0]['estimated_cost_cents_max']/100.
    price_dur = dur_step * income_per_min
    price_eta = eta_step_0 * income_per_min

    instruction = 'Take Lyft from origin to destination'
    G.add_edge(start_node, end_node,weight=price_step + price_dur + price_eta, 
                               attr_dict={'cost':price_step, 'duration':dur_step, 
                                          'mode':'lyft', 'instructions':instruction})
    G.node[start_node] = {'lat':start_lat, 'lng':start_lng}
    G.node[end_node] = {'lat':stop_lat, 'lng':stop_lng}


    # Selecting 'nodes' or 'legs' according to Google API recommendations. 
    # Moving from one leg to the next constitutes one edge in the graph.
    for leg in locator['routes'][0]['legs']:
        tot_dist = leg['distance']['value']/1000
        for cnt, steps in enumerate(leg['steps']):
            print(cnt, steps['html_instructions'])

            # Starting latitude and longitude of the node
            step_lat, step_lng = steps['start_location']['lat'], steps['start_location']['lng']

            if cnt in G.nodes():
                G.node[cnt] = {'lat':step_lat, 'lng':step_lng}
            else:
                G.add_node(cnt, {'lat':step_lat, 'lng':step_lng})

            if cnt != 0 and not 'WALKING' in leg['steps'][cnt-1]['travel_mode']:
                mode = 'lyft'
                lyft_r_step = lyft_request(start_lat, start_lng, step_lat, step_lng, token, rtype='lyft').json()

                dur_step = lyft_r_step['cost_estimates'][0]['estimated_duration_seconds']/60.
                price_step = lyft_r_step['cost_estimates'][0]['estimated_cost_cents_max']/100.
                
                price_dur = dur_step * income_per_min
                price_eta = eta_step_0 * income_per_min

                if 'WALKING' in steps['travel_mode']:
                    step_name = steps['html_instructions'].strip("Walk to")
                else:
                    step_name = steps['transit_details']['arrival_stop']['name']

                instruction = 'Take Lyft from origin to ' + step_name
                G.add_edge(start_node, cnt, weight=price_step + price_dur + price_eta, 
                               attr_dict={'cost':price_step, 'duration':dur_step, 
                                          'mode':mode, 'instructions':instruction})

                lyft_r_eta = lyft_eta(step_lat, step_lng, token, rtype='lyft').json()
                eta_step = lyft_r_eta['eta_estimates'][0]['eta_seconds']/60.

                lyft_r_step = lyft_request(step_lat, step_lng, stop_lat, stop_lng, token, rtype='lyft').json()
                dur_step = lyft_r_step['cost_estimates'][0]['estimated_duration_seconds']/60.
                price_step = lyft_r_step['cost_estimates'][0]['estimated_cost_cents_max']/100.
                
                price_dur = dur_step * income_per_min
                price_eta = eta_step * income_per_min


                instruction = 'Take Lyft from ' + step_name + " to destination"
                G.add_edge(cnt, end_node, weight=price_step + price_dur + price_eta, 
                               attr_dict={'cost':price_step, 'duration':dur_step, 
                                          'mode':mode, 'instructions':instruction})
                            
                

            if 'WALKING' in steps['travel_mode']:
                mode = 'walking'

                price_step = 0.
                dur_step = steps['duration']['value']/60
                price_dur = dur_step * income_per_min * 1.5
                price_eta = 5 * income_per_min * 1.5
                
                G.add_edge(cnt, cnt+1, weight=price_step + price_dur + price_eta, 
                               attr_dict={'cost':price_step, 'duration':dur_step, 
                                          'mode':mode, 'instructions':steps['html_instructions']})

                
            if 'TRANSIT' in steps['travel_mode']:
                mode = 'transit'

                trans_det = steps['transit_details']['line']
                trans_short_name = trans_det['short_name']
                trans_name = trans_det['vehicle']['name']
                trans_type = trans_det['vehicle']['type']

                if 'PATH' in [trans_short_name,trans_name,trans_type]: price_step = fare_info['PATH']
                elif 'SUBWAY' in [trans_short_name,trans_name,trans_type]: price_step = fare_info['SUBWAY']
                elif 'BUS' in [trans_short_name,trans_name,trans_type]: price_step = fare_info['BUS']

                dur_step = steps['duration']['value']/60            
                price_dur = dur_step * income_per_min
                price_eta = 5 * income_per_min * 1.5
                
                G.add_edge(cnt, cnt+1, weight=price_step + price_dur + price_eta, 
                               attr_dict={'cost':price_step, 'duration':dur_step, 
                                          'mode':mode, 'instructions':steps['html_instructions']})

    shortest = nx.dijkstra_path(G, source=start_node,target=end_node, weight='weight')
    print(shortest)

    return G, shortest

#===========================================================================================
def get_tract_num(olat, olong):
    url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    params = {'x': olong, 'y': olat,
            'benchmark':4,'vintage':4,'format':'json'}
    r = requests.get(url, params=params)

    return int(r.json()['result']['geographies']['Census Tracts'][0]['GEOID'])

#===========================================================================================
def google_init(origin,dest, api_key):
    url = 'https://maps.googleapis.com/maps/api/directions/json'
    pars = {'origin':origin,'destination':dest,'mode':'transit','key':api_key}
    r = requests.get(url, params=pars)

    if r.json()['status'] == 'OK':
        locator = r.json()
    else:
        return render_template("error.html", \
            errors="check the address and try again.")

    return locator

#===========================================================================================
def lyft_init():
    url = 'https://api.lyft.com/oauth/token'
    client_id = os.environ.get('Lyft_Client_ID')
    client_secret = os.environ.get('Lyft_Client_Secret') 

    # define request parameters
    payload = {"Content-Type": "application/json",
               "grant_type": "client_credentials",
               "scope": "public"}

    # request data
    res = requests.post(url,
                        data = payload,
                        auth = (client_id, client_secret))

    # extract the token from the response
    token = res.json()['access_token']

    return token

#===========================================================================================
def lyft_request(org_lat, org_long, end_lat, end_long, token, rtype='lyft'):
    query_url = 'https://api.lyft.com/v1/cost?'

    header = {"Authorization": "Bearer {}".format(token)}

    query = query_url + 'start_lat={:.4f}&start_lng={:.4f}&end_lat={:.4f}&end_lng={:.4f}&ride_type={}'\
            .format(org_lat,org_long,end_lat,end_long,rtype)

    r = requests.get(query, headers=header)

    return r

#===========================================================================================
def lyft_eta(org_lat, org_long, token, rtype='lyft'):
    query_url = 'https://api.lyft.com/v1/eta'
    header = {"Authorization": "Bearer {}".format(token)}
    payload = {'lat':org_lat, 'lng':org_long, 
               'ride_type':rtype
              }
    r = requests.get(query_url, params=payload, headers=header)
    return r

#===========================================================================================
def make_plot(short, G):

    lats = nx.get_node_attributes(G,'lat')
    longs = nx.get_node_attributes(G,'lng')

    points = []
    for node in short:
        points.append(tuple([lats[node], longs[node]]))
    ave_lat = sum(p[0] for p in points)/len(points)
    ave_lon = sum(p[1] for p in points)/len(points)

    my_map = folium.Map(location=[ave_lat,ave_lon], zoom_start=11)
    folium.Marker([lats[short[0]], longs[short[0]]]).add_to(my_map)
    folium.Marker([lats[short[-1]], longs[short[-1]]]).add_to(my_map)

    #fadd lines
    for point in points:
        folium.RegularPolygonMarker(point,
            fill_color='#132b5e',
            number_of_sides=10,
            radius=5).add_to(my_map)
    folium.PolyLine(points, color="black", weight=5, opacity=1).add_to(my_map)
    my_map.save('templates/map_final.html')

    return 

#===========================================================================================
@app.route('/about')
def about():
  return render_template('about.html')

#===========================================================================================
if __name__ == '__main__':
  app.run(host='0.0.0.0',port=33507, debug=True)
