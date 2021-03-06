def insert_user_information(api_user, count):
    """
    Insert all user-related information in the user dcollection
    :param api_user: user object from twitter API
    :param count: count of users that have been inserted in the base since the last restart/error.
    :return: count + 1 if the user is inserted, count if he has not been inserted
    Especially useful for keeping track on the process.
    """


    # Initialization of the document that is going to be inserted in the base
    user = {}
    user['id'] = api_user.id

    user['location'] = api_user.location
    user['nb_tweets'] = api_user.statuses_count
    user['nb_followers'] = api_user.followers_count
    user['description'] = api_user.description
    db.users.insert_one(user)


    # Call a function to insert this user's tweet as well
    insert_tweet_information(user['id'])

    # Add 1 to count because a user has been inserted and show some logs
    count += 1
    print('User has been inserted')

    return count


def insert_tweet_information(user_id):
    """
    Insert in the collection tweets the last 3200 tweets of a user described by his user_id.
    Here it's a bit tricky because the twitter API forces to take only 200 users at a time
    :param user_id: the id of the user whose tweets we want to insert in the database
    """

    # Initialize the structure will contain all the tweets (maximum 3200) of the user
    # This is what is going to be inserted in the database
    alltweets = []

    # make initial request for most recent tweets (200 is the maximum allowed count)
    try:
        new_tweets = api.user_timeline(user_id=user_id, count=200)

        # save most recent tweets in the data structure
        alltweets.extend(new_tweets)

        # save the id of the oldest tweet less one. Exception can occur if the number of tweets is 0
        try:
            oldest = alltweets[-1].id - 1
        except IndexError:
            oldest = len(alltweets)

        # keep grabbing tweets until there are no tweets left to grab
        while len(new_tweets) > 0:  # We retrieve all the tweets of that user until we reach the end

            # all subsequent requests use the max_id param to prevent duplicates
            new_tweets = api.user_timeline(user_id=user_id, count=200, max_id=oldest)

            # save most recent tweets
            alltweets.extend(new_tweets)

            # update the id of the oldest tweet less one
            try:
                oldest = alltweets[-1].id - 1
            except IndexError:
                pass
            print(' 200 tweets added')

        # Build the documents which are going to be inserted in the database and insert them
        for tweet in alltweets:
            tweet_object = {}
            tweet_object['tweet_id'] = tweet.id
            tweet_object['user_id'] = user_id
            tweet_object['message'] = tweet.text
            tweet_object['hashtag'] = tweet.entities['hashtags']
            tweet_object['date'] = tweet.created_at

            db.tweets.insert(tweet_object)
        print('Total: %d tweets added' % len(alltweets))

    except tweepy.error.TweepError:
        pass


def extract_information(nb_users):
    """
    Extract information from twitter to fill both databases
    The functions calls the function insert_user_information
    on each user provided we have not reached the limit of users we want to add
    :param label:0 or 1, depending wether he is a Hillary follower or a Trump follower (Hillary = 1, Trump = 0)
    :param nb_users: number of user we want to grab at one go
    """

    # Initialize the count of users, both to be able to choose the number of users we want in one go
    # and to get some logs about the evolution of the process
    count = 0

    # Repeat until we have reached the right number of users
    while count < nb_users:

        # Each user we take is initially from twitter followers
        followers = twitter_account.followers_ids()

        # Then we loop on all user in the followers
        for user in followers:
            if count < nb_users:
                # Tweeter object that describes a user
                api_user = api.get_user(id=user)

                # The users that are selected verify all those conditions:
                # Have more than 100 tweets
                # In timezone US
                # Language is english
                # Have not already been inserted
                if len(api_user.location) > 0 \
                        and api_user.statuses_count > 100 \
                        and not (api_user.time_zone is None) \
                        and 'US' in api_user.time_zone \
                        and api_user.lang == 'en' \
                        and not [i for i in db.users.find({'id': user})]:
                    count = insert_user_information(api_user, count)
                    print(count)

                #More logs
                else:
                    print('User %d: Irrelevant user' % count)
                # We delete the twitter object to make sure the RAM is not saturated
                del api_user
            else:
                break


# Script's main
if __name__ == "__main__":
    # import all the necessary libraries
    import logging
    import tweepy
    import time
    import logging
    from pymongo import MongoClient
    import json

    # Each machine has its owns credentials, so there is a json file on each computer that contains the credentials
    # This is useful to make sure we can share the code on git and keep the same code even having different credentials
    filename = "C:/token/access.json"
    with open(filename) as file:
        token = json.load(file)

    # Logging on the twitter API. This is mandatory to be able to use it
    auth = tweepy.OAuthHandler(token["consumer_key"], token["consumer_secret"])
    auth.set_access_token(token["access_key"], token["access_secret"])

    # Initializing the connection to the mongo database
    # This requires the mongo instance to be running
    client = MongoClient()
    db = client['sample']


    # Main Twitter object to make the queries
    # Note that the API also provides a sleep method if the Twitter Rate Limit is reached
    # So if this limit is reached, the API is just going to wait until it is allowed to load data again
    api = tweepy.API(auth, wait_on_rate_limit=True)

    # Twitter's account
    # We use twitter account to get users which we don't know a priori
    twitter_account = api.get_user('Twitter')

    # To get regular information about the state of the process it is necessary to keep track of the time
    start_time = time.time()

    # This loop makes sure that the computer is constantly trying to retrieve the data
    # Every time an error occurs, it is caught and the process will stop for a minute
    # This is especially useful to catch errors we can't really predict such as
    # Internet interruption, or special Twitter errors
    while 1:

        try:

            # This part makes sure that we can inform about the state of the process
            # even if we don't have access to our computer
            # Whenever the time elapsed is greater than an hour, a status is published on the twitter account
            # (defined by the token). This allows checking the process on our mobile phone
            if time.time() - start_time > 3600:
                api.update_status('''US Information Extraction :\n Users in the base : %d
                \n Tweets in the sample base : %d \n ''' % (db.users.find().count(), db.tweets.find().count()))
                start_time = time.time()

            # Call the function that insert the given number of profiles in the database
            extract_information(5000)

        # This is the part that handles unpredicted errors
        # Retry after a minute but still print the stacktrace
        except Exception as e:
            logging.error(e, exc_info=True)
            print('I sleep')
            time.sleep(60)
            pass

    print(time.time() - start_time)