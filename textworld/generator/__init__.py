# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.


import os
import json
import numpy as np
from os.path import join as pjoin
from typing import Optional, Mapping, Dict

from numpy.random import RandomState

from textworld import g_rng
from textworld.utils import maybe_mkdir, str2bool
from textworld.generator.chaining import ChainingOptions, sample_quest
from textworld.generator.game import Game, Quest, World
from textworld.generator.graph_networks import create_map, create_small_map
from textworld.generator.text_generation import generate_text_from_grammar

from textworld.generator import inform7
from textworld.generator.inform7 import generate_inform7_source, compile_inform7_game
from textworld.generator.inform7 import CouldNotCompileGameError

from textworld.generator.data import load_data
from textworld.generator.text_grammar import Grammar
from textworld.generator.maker import GameMaker
from textworld.generator.logger import GameLogger


class TextworldGenerationWarning(UserWarning):
    pass


def make_map(n_rooms, size=None, rng=None, possible_door_states=["open", "closed", "locked"]):
    """ Make a map.

    Parameters
    ----------
    n_rooms : int
        Number of rooms in the map.
    size : tuple of int
        Size (height, width) of the grid delimiting the map.
    """
    rng = g_rng.next() if rng is None else rng

    if size is None:
        edge_size = int(np.ceil(np.sqrt(n_rooms + 1)))
        size = (edge_size, edge_size)

    map = create_map(rng, n_rooms, size[0], size[1], possible_door_states)
    return map


def make_small_map(n_rooms, rng=None, possible_door_states=["open", "closed", "locked"]):
    """ Make a small map.

    The map will contains one room that connects to all others.

    Parameters
    ----------
    n_rooms : int
        Number of rooms in the map (maximum of 5 rooms).
    possible_door_states : list of str, optional
        Possible states doors can have.
    """
    rng = g_rng.next() if rng is None else rng

    if n_rooms > 5:
        raise ValueError("Nb. of rooms of a small map must be less than 6 rooms.")

    map_ = create_small_map(rng, n_rooms, possible_door_states)
    return map_


def make_world(world_size, nb_objects=0, rngs=None):
    """ Make a world (map + objects).

    Parameters
    ----------
    world_size : int
        Number of rooms in the world.
    nb_objects : int
        Number of objects in the world.
    """
    if rngs is None:
        rngs = {}
        rng = g_rng.next()
        rngs['rng_map'] = RandomState(rng.randint(65635))
        rngs['rng_objects'] = RandomState(rng.randint(65635))

    map_ = make_map(n_rooms=world_size, rng=rngs['rng_map'])
    world = World.from_map(map_)
    world.set_player_room()
    world.populate(nb_objects=nb_objects, rng=rngs['rng_objects'])
    return world


def make_world_with(rooms, rng=None):
    """ Make a world that contains the given rooms.

    Parameters
    ----------
    rooms : list of textworld.logic.Variable
        Rooms in the map. Variables must have type 'r'.
    """
    map = make_map(n_rooms=len(rooms), rng=rng)
    for (n, d), room in zip(map.nodes.items(), rooms):
        d["name"] = room.name

    world = World.from_map(map)
    world.set_player_room()
    return world


def make_quest(world, quest_length, rng=None, rules_per_depth=(), backward=False):
    state = world
    if hasattr(world, "state"):
        state = world.state

    rng = g_rng.next() if rng is None else rng

    # Sample a quest according to quest_length.
    options = ChainingOptions()
    options.backward = backward
    options.max_depth = quest_length
    options.rng = rng
    options.rules_per_depth = rules_per_depth
    chain = sample_quest(state, options)
    return Quest(chain.actions)


def make_grammar(flags: Mapping = {}, rng: Optional[RandomState] = None) -> Grammar:
    rng = g_rng.next() if rng is None else rng
    grammar = Grammar(flags, rng)
    grammar.check()
    return grammar


def make_game_with(world, quests=None, grammar=None):
    game = Game(world, grammar, quests)
    if grammar is None:
        for var, var_infos in game.infos.items():
            var_infos.name = var.name
    else:
        game = generate_text_from_grammar(game, grammar)

    return game


def make_game(world_size: int, nb_objects: int, quest_length: int, quest_breadth: int,
              grammar_flags: Mapping = {},
              rngs: Optional[Dict[str, RandomState]] = None
              ) -> Game:
    """
    Make a game (map + objects + quest).

    Arguments:
        world_size: Number of rooms in the world.
        nb_objects: Number of objects in the world.
        quest_length: Minimum nb. of actions the quest requires to be completed.
        quest_breadth: How many branches the quest can have.
        grammar_flags: Options for the grammar.

    Returns:
        Generated game.
    """
    if rngs is None:
        rngs = {}
        rng = g_rng.next()
        rngs['rng_map'] = RandomState(rng.randint(65635))
        rngs['rng_objects'] = RandomState(rng.randint(65635))
        rngs['rng_quest'] = RandomState(rng.randint(65635))
        rngs['rng_grammar'] = RandomState(rng.randint(65635))

    # Generate only the map for now (i.e. without any objects)
    world = make_world(world_size, nb_objects=0, rngs=rngs)

    # Sample a quest according to quest_length.
    class Options(ChainingOptions):

        def get_rules(self, depth):
            if depth == 0:
		        # Last action should not be "go <dir>".
                return data.get_rules().get_matching("^(?!go.*).*")
            else:
                return super().get_rules(depth)

    options = Options()
    options.backward = True
    options.min_depth = 1
    options.max_depth = quest_length
    options.min_breadth = 1
    options.max_breadth = quest_breadth
    options.create_variables = True
    options.rng = rngs['rng_quest']
    options.restricted_types = {"r", "d"}
    chain = sample_quest(world.state, options)

    subquests = []
    for i in range(1, len(chain.nodes)):
        if chain.nodes[i].breadth != chain.nodes[i - 1].breadth:
            quest = Quest(chain.actions[:i])
            subquests.append(quest)

    quest = Quest(chain.actions)
    subquests.append(quest)

    # Set the initial state required for the quest.
    world.state = chain.initial_state

    # Add distractors objects (i.e. not related to the quest)
    world.populate(nb_objects, rng=rngs['rng_objects'])

    grammar = make_grammar(grammar_flags, rng=rngs['rng_grammar'])
    game = make_game_with(world, subquests, grammar)
    game.change_grammar(grammar)

    return game


def compile_game(game: Game, game_name: Optional[str] = None,
                 metadata: Mapping = {},
                 game_logger: Optional[GameLogger] = None,
                 games_folder: str = "./gen_games",
                 force_recompile: bool = False,
                 file_type: str = ".ulx"
                 ) -> str:
    """
    Compile a game.

    Arguments:
        game: Game object to compile.
        game_name: Name of the compiled file (without extension).
            If `None`, a unique name will be infered from the game object.
        metadata: (Deprecated) contains information about how the game
            object was generated.
        game_logger: Object used to log stats about generated games.
        games_folder: Path to the folder where the compiled game will
            be saved.
        force_recompile: If `True`, recompile game even if it already
            exists.
        file_type: Either .z8 (Z-Machine) or .ulx (Glulx).

    Returns:
        The path to compiled game.
    """
    game_name = game_name or game.metadata["uuid"]
    source = generate_inform7_source(game)
    maybe_mkdir(games_folder)

    if str2bool(os.environ.get("TEXTWORLD_FORCE_ZFILE", False)):
        file_type = ".z8"

    game_json = pjoin(games_folder, game_name + ".json")
    meta_json = pjoin(games_folder, game_name + ".meta")
    game_file = pjoin(games_folder, game_name + file_type)

    already_compiled = False  # Check if game is already compiled.
    if not force_recompile and os.path.isfile(game_file) and os.path.isfile(game_json):
        already_compiled = game == Game.load(game_json)
        msg = ("It's highly unprobable that two games with the same id have different structures."
               " That would mean the generator has been modified."
               " Please clean already generated games found in '{}'.".format(games_folder))
        assert already_compiled, msg

    if not already_compiled or force_recompile:
        json.dump(metadata, open(meta_json, 'w'))
        game.save(game_json)
        compile_inform7_game(source, game_file)

    if game_logger is not None:
        game_logger.collect(game)

    return game_file


# On module load.
load_data()
