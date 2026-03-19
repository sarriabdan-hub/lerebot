/**
 * Project Assignment 3, Task e: Abstract Game class
 * 
 * Projekt 04, Task a: MVC Pattern - Controller Package
 * 
 * This class is part of the CONTROLLER layer in the Model-View-Controller pattern.
 * The controller package manages game flow and user input:
 * - Game: Abstract class for game flow control
 * - ConsoleGame, FrameGame: Specific implementations for console and GUI
 * - Player: Abstract class for player actions  
 * - ConsolePlayer, MocPlayer, FramePlayer: Different player implementations
 * 
 * Controllers coordinate between the model (game logic) and view (user interface),
 * handling user input and updating the game state accordingly.
 * 
 * This abstract class manages the overall game structure, including
 * the game board, two players, and tracking which player's turn it is.
 * Subclasses must implement the specific game flow logic.
 * 
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Board;

/**
 * Project Assignment 3 - Task e
 * Abstract class representing the game logic.
 */
public abstract class Game {

    // Task e, Part 1: A reference to the board
    protected Board board;
    
    // Task e, Part 2: A reference to each of the two players
    protected Player player1;
    protected Player player2;
    
    // Task e, Part 3: Store which player is currently taking their turn
    protected Player currentPlayer;

    /**
     * Task e, Part 4: Constructor with Board as parameter
     * 
     * @param board The game board
     */
    public Game(Board board) {
        this.board = board;
    }

    /**
     * Task e, Part 5: Method to change the current player
     * 
     * Swaps between player1 and player2.
     */
    protected void swapPlayer() {
        if (currentPlayer == player1) {
            currentPlayer = player2;
        } else {
            currentPlayer = player1;
        }
    }

    /**
     * Task e, Part 6: Abstract method where actual game flow is defined
     * 
     * This method must be implemented by subclasses to define
     * the specific game loop and win conditions.
     */
    public abstract void doGame();
}
