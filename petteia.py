#!/usr/bin/env python3
"""Petteia（古希腊棋）——8x8 夹吃棋，custodian capture，无棋可走判负。

规则为依据零散史料的重构版本（README 诚实说明）：
- 8x8 棋盘，双方各 8 子：甲占第 0 行，乙占第 7 行。
- 每回合走一子，沿横/竖直线走任意格（车式），不能跳子。
- 夹吃：走子落定后，与其正交相邻的敌子，若另一侧紧贴己子，则被吃掉。
  （主动把自己的子走到两敌子之间不算自杀。）
- 吃光对方子，或对方轮到时无合法走法，即获胜。
- 同一局面出现三次判和；设步数上限防无限对局，撞上限判和棋。
"""

import argparse
import copy
import random
import sys

SIZE = 8
EMPTY = 0
P0 = 1  # 甲（先手）
P1 = 2  # 乙
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
PIECES_PER_SIDE = 8
MAX_MOVES = 300  # 半回合上限，撞上限判和
GLYPH = {EMPTY: "·", P0: "●", P1: "○"}


def other(player):
    return P1 if player == P0 else P0


def in_bounds(r, c):
    return 0 <= r < SIZE and 0 <= c < SIZE


class Petteia:
    def __init__(self):
        self.board = [[EMPTY] * SIZE for _ in range(SIZE)]
        for c in range(SIZE):
            self.board[0][c] = P0
            self.board[SIZE - 1][c] = P1
        self.n_moves = 0

    def pieces(self, player):
        return [(r, c) for r in range(SIZE) for c in range(SIZE)
                if self.board[r][c] == player]

    def count(self, player):
        return len(self.pieces(player))

    def legal_moves(self, player):
        """全部合法走法：((from_r, from_c), (to_r, to_c))。"""
        moves = []
        for fr, fc in self.pieces(player):
            for dr, dc in DIRS:
                r, c = fr + dr, fc + dc
                while in_bounds(r, c) and self.board[r][c] == EMPTY:
                    moves.append(((fr, fc), (r, c)))
                    r, c = r + dr, c + dc
        return moves

    def capture_squares(self, player, tr, tc):
        """走子落到 (tr,tc) 后被夹吃的敌子坐标（纯函数，不改棋盘）。"""
        foe = other(player)
        caps = []
        for dr, dc in DIRS:
            nr, nc = tr + dr, tc + dc
            br, bc = nr + dr, nc + dc
            if (in_bounds(nr, nc) and in_bounds(br, bc)
                    and self.board[nr][nc] == foe
                    and self.board[br][bc] == player):
                caps.append((nr, nc))
        return caps

    def apply_move(self, player, move):
        """执行走法，返回吃掉的子数。非法走法抛 ValueError。"""
        (fr, fc), (tr, tc) = move
        if not (in_bounds(fr, fc) and in_bounds(tr, tc)):
            raise ValueError(f"坐标越界: {move}")
        if self.board[fr][fc] != player:
            raise ValueError(f"起点不是己方棋子: {move}")
        if self.board[tr][tc] != EMPTY:
            raise ValueError(f"落点被占: {move}")
        dr = (tr > fr) - (tr < fr)
        dc = (tc > fc) - (tc < fc)
        if (dr, dc) not in DIRS:
            raise ValueError(f"必须横/竖走直线: {move}")
        r, c = fr + dr, fc + dc
        while (r, c) != (tr, tc):
            if self.board[r][c] != EMPTY:
                raise ValueError(f"路径被挡: {move}")
            r, c = r + dr, c + dc
        self.board[fr][fc] = EMPTY
        self.board[tr][tc] = player
        captured = 0
        for cr, cc in self.capture_squares(player, tr, tc):
            self.board[cr][cc] = EMPTY
            captured += 1
        self.n_moves += 1
        return captured

    def winner(self, player_to_move):
        """返回胜者 P0/P1，0 表和/未定由调用方结合步数判断。"""
        if self.count(P0) == 0:
            return P1
        if self.count(P1) == 0:
            return P0
        if not self.legal_moves(player_to_move):
            return other(player_to_move)
        return 0

    def render(self):
        head = "  " + " ".join(str(c) for c in range(SIZE))
        lines = [head]
        for r in range(SIZE):
            lines.append(f"{r} " + " ".join(GLYPH[self.board[r][c]]
                                           for c in range(SIZE)))
        return "\n".join(lines)


def ai_choose(game, player, rng, seen=None):
    """1 步贪心：吃子 > 避重复局面 > 贴近敌子 > 落点威胁 > 机动性差 > 向中心靠。"""
    moves = game.legal_moves(player)
    if not moves:
        return None
    seen = seen or {}
    best, best_key = None, None
    foe = other(player)
    for mv in moves:
        sim = copy.deepcopy(game)
        captured = sim.apply_move(player, mv)
        (fr, fc), (tr, tc) = mv
        foes = sim.pieces(foe)
        dmin = min(abs(tr - r) + abs(tc - c) for r, c in foes) if foes else 0
        adj = sum(1 for dr, dc in DIRS
                  if in_bounds(tr + dr, tc + dc)
                  and sim.board[tr + dr][tc + dc] == foe)
        my_mob = len(sim.legal_moves(player))
        foe_mob = len(sim.legal_moves(foe))
        center = abs(tr - 3.5) + abs(tc - 3.5)
        rep = seen.get((tuple(tuple(row) for row in sim.board), foe), 0)
        key = (captured, -rep, -dmin, adj, my_mob - foe_mob,
               -center, rng.random())
        if best_key is None or key > best_key:
            best, best_key = mv, key
    return best


def board_key(game, turn):
    return (tuple(tuple(row) for row in game.board), turn)


def play_auto(games=1, seed=0, verbose=False):
    rng = random.Random(seed)
    w0 = w1 = draws = 0
    for gi in range(games):
        g = Petteia()
        turn = P0
        seen = {}
        result = 0
        while g.n_moves < MAX_MOVES:
            result = g.winner(turn)
            if result:
                break
            key = board_key(g, turn)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= 3:
                break  # 三次重复局面判和
            mv = ai_choose(g, turn, rng, seen)
            if mv is None:
                result = other(turn)
                break
            g.apply_move(turn, mv)
            turn = other(turn)
        if result == P0:
            w0 += 1
            tag = "甲胜"
        elif result == P1:
            w1 += 1
            tag = "乙胜"
        else:
            draws += 1
            tag = "和棋"
        if verbose or games <= 10:
            print(f"第 {gi + 1}/{games} 局：{tag}（{g.n_moves} 半回合，"
                  f"甲{g.count(P0)}子/乙{g.count(P1)}子）")
    print(f"总计：甲胜 {w0}，乙胜 {w1}，和棋 {draws}")
    return w0, w1, draws


def parse_coord(s):
    try:
        r, c = s.strip().split(",")
        r, c = int(r), int(c)
    except ValueError:
        raise ValueError("坐标格式应为 行,列，如 2,3")
    if not in_bounds(r, c):
        raise ValueError("坐标越界")
    return r, c


def play_interactive():
    if not sys.stdin.isatty():
        print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
        sys.exit(2)
    g = Petteia()
    rng = random.Random()
    human = P0
    print("Petteia 古希腊棋：你是 ●（甲），AI 是 ○（乙）。输入如 0,3 2,3 走子，q 退出。")
    turn = P0
    while g.n_moves < MAX_MOVES:
        result = g.winner(turn)
        if result:
            break
        print("\n" + g.render())
        if turn == human:
            print(f"轮到你（甲 ●），剩余子 甲{g.count(P0)}/乙{g.count(P1)}")
            try:
                s = input("走法（起点终点，q退出）> ").strip()
            except EOFError:
                break
            if s.lower() == "q":
                break
            try:
                a, b = s.split()
                mv = (parse_coord(a), parse_coord(b))
                n = g.apply_move(human, mv)
                print(f"走了，吃掉 {n} 子" if n else "走了")
            except ValueError as e:
                print("非法走法：", e)
                continue
        else:
            mv = ai_choose(g, P1, rng)
            if mv is None:
                result = P0
                break
            n = g.apply_move(P1, mv)
            (fr, fc), (tr, tc) = mv
            print(f"AI: ({fr},{fc})->({tr},{tc})" + (f"，吃掉 {n} 子" if n else ""))
        turn = other(turn)
    print("\n" + g.render())
    if result == P0:
        print("你赢了！")
    elif result == P1:
        print("AI 赢了。")
    else:
        print("和棋。")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Petteia 古希腊夹吃棋")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=1, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verbose", action="store_true", help="自动演示打印棋盘")
    args = ap.parse_args(argv)
    if args.auto:
        play_auto(games=args.games, seed=args.seed, verbose=args.verbose)
    else:
        play_interactive()


if __name__ == "__main__":
    main()
