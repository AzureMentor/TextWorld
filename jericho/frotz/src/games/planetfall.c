// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.


#include <string.h>
#include "frotz.h"
#include "games.h"
#include "frotz_interface.h"

// Planetfall: http://ifdb.tads.org/viewgame?id=xe6kb3cuqwie2q38

char** planetfall_intro_actions(int *n) {
  *n = 0;
  return NULL;
}

char* planetfall_clean_observation(char* obs) {
  char* pch;
  pch = strchr(obs, '\n');
  if (pch != NULL) {
    return pch+1;
  }
  return obs;
}

int planetfall_victory() {
  char *death_text = "****  You have won  ****";
  if (strstr(world, death_text)) {
    return 1;
  }
  return 0;
}

int planetfall_game_over() {
  char *death_text = "****  You have died  ****";
  if (strstr(world, death_text)) {
    return 1;
  }
  return 0;
}

int planetfall_get_self_object_num() {
  return 236;
}

int planetfall_get_moves() {
  return (((short) zmp[10473]) << 8) | zmp[10474];
}

int planetfall_get_score() {
  return zmp[10026];
}

int planetfall_max_score() {
  return 80;
}

int planetfall_get_num_world_objs() {
  return 252;
}

int planetfall_ignore_moved_obj(zword obj_num, zword dest_num) {
  return 0;
}

int planetfall_ignore_attr_diff(zword obj_num, zword attr_idx) {
  return 0;
}

int planetfall_ignore_attr_clr(zword obj_num, zword attr_idx) {
  return 0;
}
