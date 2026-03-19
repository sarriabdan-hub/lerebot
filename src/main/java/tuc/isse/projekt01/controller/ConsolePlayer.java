/**
 * Project Assignment 3, Task d: ConsolePlayer class
 * 
 * This class represents a human player who interacts with the game
 * through the console. It prompts the user to input their moves
 * (ball position and direction) and executes them on the board.
 * 
 * The implementation is robust and handles all exceptions that
 * may be thrown by the moveBall method.
 * 
 * @author xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01.controller;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;
import java.util.Scanner;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;

/**
 * Table 8, Project Assignment 3 - Task d
 * Console-based interactive player implementation.
 */
public class ConsolePlayer extends Player {

    // Task d, Part 3: BufferedReader for reading console input
    private BufferedReader consoleReader;

    /**
     * Constructor for ConsolePlayer
     * 
     * @param color The color of this player
     * @param board The game board reference
     */
    public ConsolePlayer(Color color, Board board) {
        super(color, board);
        // Task d, Part 3: Initialize BufferedReader for console input
        this.consoleReader = new BufferedReader(new InputStreamReader(System.in));
    }

    /**
     * Task d, Part 1: Interactive implementation of doTurn()
     * 
     * Queries the position of the ball and desired direction via console,
     * then calls moveBall from Board.
     * 
     * Task d, Part 2: Robust design with exception handling
     */
    @Override
    public void doTurn() {

        while (true) {

            try {
                System.out.println("Current Player: " + color);
                // Task d, Part 1: Query ball position and direction from console
                System.out.print("Enter move (Example: 0 3 DOWN): ");
                
                // Task d, Part 4: Read input using readLine()
                String input = consoleReader.readLine();

                if (input == null || input.trim().isEmpty()) {
                    System.out.println("Empty input. Try again.");
                    continue;
                }

                try (Scanner scanner = new Scanner(input)) {
                    // Parse column, row, and direction from input
                    int col = scanner.nextInt();
                    int row = scanner.nextInt();
                    String dirString = scanner.next();

                    Direction direction =
                            Direction.valueOf(dirString.toUpperCase());

                    // Task d, Part 1: Call moveBall from Board
                    board.moveBall(color, col, row, direction);

                    // Task d, Part 2: Successful move - end turn
                    break;
                }
            // Task d, Part 2: Handle exceptions thrown by moveBall
            } catch (NotYourBallException e) {
                System.out.println("There is no ball of your color in the specified cell. Please try again.");
            } catch (NotInRangeException e) {
                System.out.println("The specified row or column does not exist. Please try again.");
            } catch (OutOfGameException e) {
                System.out.println("Your ball cannot be moved outside the game board. Please try again.");
            } catch (IllegalArgumentException e) {
                System.out.println("Invalid direction! Use UP, DOWN, LEFT, RIGHT.");
            } catch (IOException e) {
                System.out.println("Input error.");
            } catch (Exception e) {
                System.out.println("Invalid input format. Example: 0 3 DOWN");
            }
        }
    }
}