#!/usr/bin/python
from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc, desc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Games, Items, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
app = Flask(__name__)
CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Games Items Application"


engine = create_engine('sqlite:///gameItem.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data
    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response
    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is connected'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id
    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)
    data = answer.json()
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    # See if a user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id
    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;'
    output += '-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    print "done!"
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.ids


def getUserInfo(user_id):
    user = session.query(User).filter_by(ids=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.ids
    except:
        return None


@app.route('/gdisconnect')
def gdisconnect():
        # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response
# making JSON Endpoints


@app.route('/catalog/<int:game_id>/item/JSON')
def catalogitemJSON(game_id):
    # JSON endpoints to display items of a particular items
    games = session.query(Games).filter_by(ids=game_id).one()
    items = session.query(Items).filter_by(game_id=games.ids).all()
    return jsonify(items=[i.serialize for i in items])


@app.route('/catalog/<int:game_id>/item/<int:item_id>/JSON')
def ItemJSON(game_id, item_id):
    # JSON endpoints to display the properties of a particular Item
    Item = session.query(Items).filter_by(ids=item_id).one()
    return jsonify(Item=Item.serialize)


@app.route('/catalog/JSON')
def catalogJSON():
    # JSON endpoints to display the whole catalog
    catalogs = session.query(Games).all()
    return jsonify(catalogs=[r.serialize for r in catalogs])


@app.route("/")
@app.route("/catalog")
def catalog():
    # Displays the whole catalog
    games = session.query(Games).order_by(asc(Games.name))
    items = session.query(Items).order_by(desc(Items.ids)).limit(5)
    if 'username' not in login_session:
        return render_template('publicCatalog.html', games=games, items=items)
    else:
        return render_template('Catalog.html', games=games, items=items)


@app.route("/add", methods=['GET', 'POST'])
def addCatalog():
    # used to add more categories to catalog
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newGame = Games(
                    name=request.form['name'],
                    user_id=login_session['user_id'])
        session.add(newGame)
        session.commit()
        return redirect(url_for('catalog'))
    else:
        return render_template('Catalogadd.html')


@app.route("/catalog/<int:game_id>/items")
def showitems(game_id):
    # used to display items of a particular category
    items = session.query(Items).filter_by(game_id=game_id)
    game = session.query(Games).filter_by(ids=game_id).one()
    if 'username' not in login_session:
        return render_template('publicitems.html', items=items, game=game)
    else:
        return render_template('items.html', items=items, game=game)


@app.route("/catalog/<int:game_id>/items/add", methods=['GET', 'POST'])
def additems(game_id):
    # used to add more items to catalog
    if 'username' not in login_session:
        return redirect('/login')
    game = session.query(Games).filter_by(ids=game_id).one()
    if request.method == 'POST':
        newItem = Items(
            name=request.form['name'],
            user_id=login_session['user_id'],
            game_id=game.ids)
        session.add(newItem)
        session.commit()
        return redirect(url_for('showitems', game_id=game_id))
    else:
        return render_template('addItems.html', games=game)


@app.route("/catalog/<int:game_id>/items/<int:item_id>")
def item_description(game_id, item_id):
    # description of a particular item
    items = session.query(Items).filter_by(ids=item_id).one()
    if 'username' not in login_session:
        return render_template('publicitemdescription.html', items=items)
    else:
        return render_template('itemDescription.html', items=items)


@app.route("/catalog/items/<int:item_id>/edit", methods=['GET', 'POST'])
def item_edit(item_id):
    # edit particular item
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(
        Items).filter_by(ids=item_id).one()
    er = "You are not authorized to edit this item."
    if getUserInfo(editedItem.user_id).email != login_session['email']:
        return render_template('itemDescription.html', er=er, items=editedItem)
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        return redirect(url_for('item_description',
                        game_id=editedItem.game_id,
                        item_id=item_id))
    else:
        return render_template('editItem.html', items=editedItem)


@app.route("/catalog/items/<int:item_id>/delete", methods=['GET', 'POST'])
def item_delete(item_id):
    # delete a particular item
    if 'username' not in login_session:
        return redirect('/login')
    deleteitem = session.query(
        Items).filter_by(ids=item_id).one()
    er = "You are not authorized to delete this item."
    if getUserInfo(deleteItem.user_id).email != login_session['email']:
        return render_template('itemDescription.html', er=er, items=deleteItem)
    if request.method == 'POST':
        session.delete(deleteitem)
        session.commit()
        return redirect(url_for('showitems', game_id=deleteitem.game_id))
    else:
        return render_template('deleteItem.html', items=deleteitem)


if __name__ == '__main__':
    app.secret_key = '2xbN50IXK2qSy_fiXRvYmox9'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
