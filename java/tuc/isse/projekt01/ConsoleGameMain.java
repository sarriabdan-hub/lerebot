/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 * 
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01;

import tuc.isse.projekt01.controller.ConsoleGame;
import tuc.isse.projekt01.controller.ConsolePlayer;
import tuc.isse.projekt01.controller.Player;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;

/**
 * Main Class for Console-based Game (from previous project assignments)
 * 
 * This is the console version of the game, prior to the GUI implementation.
 * It creates a standard Board, ConsolePlayer instances, and runs the game
 * through console input/output.
 */
// Table 08 Task g
public class ConsoleGameMain {

    public static void main(String[] args) {
        // Create and initialize the board with starting positions
        Board board = new Board();
        
        // Create two ConsolePlayer objects
        Player whitePlayer = new ConsolePlayer(Color.WHITE, board);
        Player blackPlayer = new ConsolePlayer(Color.BLACK, board);
        
        // Create ConsoleGame with white player starting
        ConsoleGame game = new ConsoleGame(board, whitePlayer, blackPlayer);
        
        // Execute the game
        game.doGame();
    }
}
