/**
 * Table 8, Project Assignment 3, Task f: ConsoleGame class
 * 
 * This class implements the console-based game flow. It alternates
 * between two players, asking each for their turn until there is a winner.
 * After each turn, the game board is displayed to show the current state.
 * 
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Winner;

/**
 * Project Assignment 3 - Task f
 * Console-based game implementation.
 */
public class ConsoleGame extends Game {

    /**
     * Constructor for ConsoleGame.
     * @param board The game board
     * @param whitePlayer The player with WHITE color
     * @param blackPlayer The player with BLACK color
     */
    public ConsoleGame(Board board, Player whitePlayer, Player blackPlayer) {
        super(board);
        this.player1 = whitePlayer;
        this.player2 = blackPlayer;
        // White player starts
        this.currentPlayer = (whitePlayer.getColor() == Color.WHITE) ? whitePlayer : blackPlayer;
    }

    /**
     * Task f, Part 1: Implementation of doGame()
     * 
     * Players are asked alternately for a turn (doTurn) until there is a winner.
     * 
     * Task f, Part 2: After every turn, the game field is outputted.
     */
    @Override
    public void doGame() {
        System.out.println("=== Game Start ===");
        System.out.println(board.toString());

        // Task f, Part 1: Alternate turns until there is a winner
        while (board.getWinner() == Winner.NONE) {
            // Ask current player for their turn
            currentPlayer.doTurn();
            
            // Task f, Part 2: Display the board after each turn
            System.out.println(board.toString());
            
            // Check for winner
            if (board.getWinner() != Winner.NONE) {
                break;
            }
            
            // Swap to the other player
            swapPlayer();
        }

        // Announce the winner
        Winner winner = board.getWinner();
        if (winner == Winner.WHITE) {
            System.out.println("\n*** WHITE WINS! ***");
        } else if (winner == Winner.BLACK) {
            System.out.println("\n*** BLACK WINS! ***");
        }
    }
}
