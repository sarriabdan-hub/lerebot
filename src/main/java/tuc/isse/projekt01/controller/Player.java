/**
 * Project Assignment 3, Task c: Abstract Player class
 * 
 * Projekt 04, Task a: MVC Pattern - Controller Package
 * 
 * This class is part of the CONTROLLER layer. It handles player interactions
 * and translates user input into game actions (ball movements).
 * Different implementations support different input methods:
 * - ConsolePlayer: Reads moves from console input
 * - MocPlayer: Automated player for testing
 * - FramePlayer: GUI-based player using ActionListeners (Task e)
 * 
 * This abstract class represents a player in the 90 Grad game.
 * It serves as the base class for different player implementations
 * (human players via console, automated mock players for testing, etc.).
 * 
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;

/**
 * Table 8, Project Assignment 3 - Task c
 * Abstract class representing a player in the game.
 */
public abstract class Player {

    // Task c, Part 1: The Color of the player
    protected Color color;
    
    // Task c, Part 2: A reference to the game board
    protected Board board;
    
    /**
     * Task c, Part 3: Constructor with Color and Board as parameters
     * 
     * @param color The color of this player (WHITE or BLACK)
     * @param board The game board reference
     */
    public Player(Color color, Board board) {
        this.color = color;
        this.board = board;
    }

    /**
     * @return The color of this player
     */
    public Color getColor() {
        return color;
    }

    /**
     * @return The game board reference
     */
    public Board getBoard() {
        return board;
    }

    /**
     * Task c, Part 4: Abstract method to perform a player's turn
     * 
     * This method must be implemented by subclasses to define
     * how the player makes their move (e.g., reading from console,
     * executing predefined moves, or using AI).
     */
    public abstract void doTurn();
}