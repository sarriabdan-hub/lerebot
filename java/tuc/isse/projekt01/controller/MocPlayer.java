/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 */
package tuc.isse.projekt01.controller;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;

/**
 * Project Assignment 3 - Task h
 * Mock player for automated testing with predefined move sequences.
 */
public class MocPlayer extends Player {

    // Task h, Part 1: Attribute to count the round
    private int round;
    
    // Scenario selection: which player should win
    private boolean blackWinsScenario;

    /**
     * Constructor for MocPlayer
     * 
     * @param color The color of this player
     * @param board The game board reference
     * @param blackWinsScenario true for BLACK wins scenario, false for WHITE wins scenario
     */
    public MocPlayer(Color color, Board board, boolean blackWinsScenario) {
        super(color, board);
        this.round = 0;
        this.blackWinsScenario = blackWinsScenario;
    }

    /**
     * Task h, Part 2: Implementation of doTurn() 
     * Task h, Part 3: Counts rounds 
     */
    @Override
    public void doTurn() {
        // Task h, Part 3: Count rounds
        round++;
        
        // Display round information
        System.out.println("[" + color + " MocPlayer - Round " + round + "]");
        
        // Task h, Part 2: Execute move depending on color
        if (color == Color.WHITE) {
            executeWhiteMove();
        } else {
            executeBlackMove();
        }
    }

    /**
     * Task h, Part 2 & 3: Fixed game sequence for WHITE player
     */
    private void executeWhiteMove() {
        try {
            if (blackWinsScenario) {
                // Scenario 1: BLACK WINS
                switch (round) {
                    case 1:
                        board.moveBall(Color.WHITE, 3, 0, Direction.RIGHT);
                        break;
                    case 2:
                        board.moveBall(Color.WHITE, 5, 0, Direction.DOWN);
                        break;
                    case 3:
                        board.moveBall(Color.WHITE, 1, 4, Direction.DOWN);
                        break;
                    case 4:
                        board.moveBall(Color.WHITE, 1, 6, Direction.RIGHT);
                        break;
                }
            } else {
                // Scenario 2: WHITE WINS - Based on actual game 2026-02-13
                switch (round) {
                    case 1:
                        // WHITE Turn 1: 1 0 DOWN
                        board.moveBall(Color.WHITE, 1, 0, Direction.DOWN);
                        break;
                    case 2:
                        // WHITE Turn 2: 0 0 DOWN
                        board.moveBall(Color.WHITE, 0, 0, Direction.DOWN);
                        break;
                    case 3:
                        // WHITE Turn 3: 0 3 RIGHT
                        board.moveBall(Color.WHITE, 0, 3, Direction.RIGHT);
                        break;
                    case 4:
                        // WHITE Turn 4: 2 3 RIGHT
                        board.moveBall(Color.WHITE, 2, 3, Direction.RIGHT);
                        break;
                    case 5:
                        // WHITE Turn 5: 0 3 RIGHT
                        board.moveBall(Color.WHITE, 0, 3, Direction.RIGHT);
                        break;
                    case 6:
                        // WHITE Turn 6: 4 3 LEFT - King reaches center (3,3) and WINS!
                        board.moveBall(Color.WHITE, 4, 3, Direction.LEFT);
                        break;
                }
            }
        } catch (NotYourBallException | NotInRangeException | OutOfGameException e) {
            System.err.println("MocPlayer Round " + round + " (WHITE): " + e.getMessage());
        }
    }

    /**
     * Task h, Part 2 & 3: Fixed game sequence for BLACK player
     */
    private void executeBlackMove() {
        try {
            if (blackWinsScenario) {
                // Scenario 1: BLACK WINS
                switch (round) {
                    case 1:
                        board.moveBall(Color.BLACK, 3, 6, Direction.UP);
                        break;
                    case 2:
                        board.moveBall(Color.BLACK, 6, 4, Direction.LEFT);
                        break;
                    case 3:
                        board.moveBall(Color.BLACK, 3, 2, Direction.UP);
                        break;
                    case 4:
                        board.moveBall(Color.BLACK, 3, 0, Direction.LEFT);
                        break;
                }
            } else {
                // Scenario 2: WHITE WINS - Based on actual game 2026-02-13
                switch (round) {
                    case 1:
                        // BLACK Turn 1: 4 6 UP
                        board.moveBall(Color.BLACK, 4, 6, Direction.UP);
                        break;
                    case 2:
                        // BLACK Turn 2: 4 2 DOWN
                        board.moveBall(Color.BLACK, 4, 2, Direction.DOWN);
                        break;
                    case 3:
                        // BLACK Turn 3: 5 3 LEFT
                        board.moveBall(Color.BLACK, 5, 3, Direction.LEFT);
                        break;
                    case 4:
                        // BLACK Turn 4: 6 3 LEFT
                        board.moveBall(Color.BLACK, 6, 3, Direction.LEFT);
                        break;
                    case 5:
                        // BLACK Turn 5: 3 6 UP
                        board.moveBall(Color.BLACK, 3, 6, Direction.UP);
                        break;
                }
            }
        } catch (NotYourBallException | NotInRangeException | OutOfGameException e) {
            System.err.println("MocPlayer Round " + round + " (BLACK): " + e.getMessage());
        }
    }

    /**
     * Get the current round number for testing
     * @return The current round counter
     */
    public int getRound() {
        return round;
    }
}
