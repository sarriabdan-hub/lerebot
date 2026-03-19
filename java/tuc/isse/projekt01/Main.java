package tuc.isse.projekt01;

import java.util.Scanner;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.ObservableBoard;
import tuc.isse.projekt01.model.Winner;
import tuc.isse.projekt01.view.DegreeFrame;

//import java.util.InputMismatchException;

/**
 * The entry point of the program.
 * The main game loop.
 * Task c: Alternating turns until a winner is determined.
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 */
/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
public class Main {
    public static void main(String[] args) {
        // Task c: Initialize the board and input scanner
        Board board = new Board();
        Scanner scanner = new Scanner(System.in);

        // Task c: Set the starting player (White usually starts)
        Color currentTurn = Color.WHITE;

        System.out.println("90 Grad - Game Start!");
        System.out.println("Format: [Column] [Row] [Direction]");
        System.out.println("Example: 0 3 DOWN");

        // Task c: Game Loop - continue running as long as there is NO winner
        while (board.getWinner() == Winner.NONE) {

            // Task c: Print current board state
            System.out.println("\n" + board.toString());
            System.out.println("Current Turn: " + currentTurn);
            System.out.print("Enter move (e.g., '0 3 DOWN'): ");

            try {
                // Fix: Check if input is actually a number. If not, skip this turn.
                if (!scanner.hasNextInt()) {
                    String trash = scanner.next(); // Consume the bad text
                    System.out.println("Error: '" + trash + "' is not a number! Please enter coordinates first.");
                    continue; // Restart the loop, don't exit!
                }

                // Task c: Read input coordinates
                int col = scanner.nextInt();
                int row = scanner.nextInt();

                // Task c: Read input direction
                String dirString = scanner.next();
                Direction direction = Direction.valueOf(dirString.toUpperCase());

                // Task c: Execute the move
                board.moveBall(currentTurn, col, row, direction);

                // Task c: Check winner immediately
                if (board.getWinner() != Winner.NONE) {
                    break;
                }

                // Task c: Switch turns ONLY if move was successful
                currentTurn = (currentTurn == Color.WHITE) ? Color.BLACK : Color.WHITE;

            } catch (IllegalArgumentException e) {
                System.out.println("Error: Invalid Direction! Use UP, DOWN, LEFT, RIGHT.");
            } catch (Exception e) {
                // Task c: Handle Game Rules (NotYourBall, OutOfGame, etc.)
                System.out.println("Invalid Move: " + e.getClass().getSimpleName());
                System.out.println("Try again!");
            }
        }

        // Task c: End of game
        System.out.println(board.toString());
        System.out.println("##############################");
        System.out.println("GAME OVER! The Winner is: " + board.getWinner());
        System.out.println("##############################");
        scanner.close();       
      
    }
}