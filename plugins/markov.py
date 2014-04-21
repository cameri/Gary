import re
import random
import time
import redis as redislib
from collections import Counter
from util import hook

chain_length = 2
max_words = 30
messages_to_generate = 5
separator = '<space>'
stop_word = '<stop>'

redis = redislib.Redis()


def get_seeds(message):
    words = message.split()

    if len(words) > chain_length:
        words.append(stop_word)

        for i in range(len(words) - chain_length):
            yield words[i:i + chain_length + 1]


def generate_chain(key):
    gen_words = []

    for i in xrange(max_words):
        words = key.split(separator)
        gen_words.append(words[0])
        next_word = redis.srandmember(key)
        if not next_word:
            break

        key = separator.join(words[1:] + [next_word])

    return ' '.join(gen_words)


def get_message(key):
    best_message = ''

    for i in range(messages_to_generate):
        generated = generate_chain(key)

        if len(generated) > len(best_message):
            best_message = generated

    return best_message or None


@hook.event('PRIVMSG')
def log(paraml, nick='', input=None):
    if input.msg[0] in ('.', '!') or input.chan[0] != '#' or \
            "<reply>" in input.msg.split() or nick == 'extrastout':
        return

    message = input.msg.lower()

    for words in get_seeds(message):
        key = separator.join(words[:-1])
        redis.sadd(key, words[-1])


@hook.command(autohelp=False)
def markov(inp, say=''):
    ".markov [phrase] - Generate a Markov chain randomly or based on a phrase"
    messages = []

    if inp and len(inp.split()) <= chain_length:
        for i in range(messages_to_generate):
            try:
                message = get_message(random.choice(redis.keys('*' +
                    '<space>'.join(inp.lower().split()) + '*')))
            except:
                return "I do not have enough data to " \
                    "formulate a response for that phrase"
            if message and len(message.split()) > chain_length:
                messages.append(message)
    elif len(inp.split()) > chain_length:
        for seed in get_seeds(inp.lower()):
            key = separator.join(seed[:-1])
            redis.sadd(key, seed[-1])
            message = get_message(key)
            if message and len(message.split()) > chain_length:
                messages.append(message)
    else:
        while len(messages) < messages_to_generate:
            message = get_message(redis.randomkey())
            if not message:
                break
            if len(message.split()) > chain_length:
                messages.append(message)

    if len(messages):
        say(random.choice(messages))
    else:
        return "I do not have enough data to formulate a response"


@hook.command(autohelp=False)
def rinfo(inp):
    ".rinfo - Gets Redis DB info"
    try:
        info = redis.info()
        keys = info['db0']['keys']
        mem = info['used_memory_human']
        hits = info['keyspace_hits']
        misses = info['keyspace_misses']
        commands = info['total_commands_processed']
        changes = info['rdb_changes_since_last_save']
        last_save = time.strftime('%H:%M %D', time.localtime(int(info['rdb_last_save_time'])))
        distr = {k: v for k, v in Counter(redis.scard(key) for key in redis.keys()).iteritems()}
        sets = sum([k*v for k, v in distr.iteritems()])

        out = "I have %s keys/%s associations (%s); " % (keys, sets, mem)
        out += "%s processed commands (%s hits/%s misses); " % (commands, hits, misses)
        out += "last save at %s (%s pending changes to write); " % (last_save, changes)
        return out
    except:
        return "I do not yet have enough data to generate Redis statistics"


@hook.command(adminonly=True)
def rdelete(inp):
    ".rdelete <key> - Deletes a specified key from the Redis DB"
    try:
        for key in redis.keys('*' + inp.lower() + '*'):
            redis.delete(key)
        for key in redis.keys():
            for member in redis.smembers():
                if inp.lower() in member:
                    redis.srem(key, member)
        return "Keys matching '%s' deleted" % inp
    except:
        return "Keys matching '%s' deleted" % inp


#@hook.command(autohelp=False, adminonly=True)
def rflush(inp):
    ".rflush - Flushes Redis DB and resets statistics, use with care"
    redis.flushall()
    redis.config_resetstat()
    return "Redis database flushed."
